import base64
import io
import json
import logging
import re
import textwrap
import qrcode

from bija.alerts import AlertKind
from lightning.lnaddr import lndecode

from flask import render_template, url_for
import arrow

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import get_at_tags, is_hex_key, url_linkify, strip_tags, get_invoice, get_hash_tags, is_bech32_key, \
    bech32_to_hex64
from bija.settings import SETTINGS
from bija.ws.key import PrivateKey

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


@app.template_filter('alert')
def _jinja2_filter_alert(kind, data):
    data = json.loads(data)
    tpl = None
    if kind == AlertKind.REPLY:
        data['profile'] = DB.get_profile(data['public_key'])
        tpl = 'reply'
    if kind == AlertKind.COMMENT_ON_THREAD:
        data['profile'] = DB.get_profile(data['public_key'])
        tpl = 'thread_comment'
    if kind == AlertKind.REACTION:
        data['profile'] = DB.get_profile(data['public_key'])
        data['note'] = DB.get_note(SETTINGS.get('pubkey'), data['referenced_event'])
        tpl = 'reaction'
    if kind == AlertKind.FOLLOW:
        data['profile'] = DB.get_profile(data['public_key'])
        tpl = 'follow'
    if kind == AlertKind.UNFOLLOW:
        data['profile'] = DB.get_profile(data['public_key'])
        tpl = 'unfollow'

    if tpl is not None:
        return render_template('alerts/{}.html'.format(tpl), data=data)
    else:
        return 'failed to load alert'

@app.template_filter('svg_icon')
def _jinja2_filter_svg(icon, class_name):
    return render_template('svg/{}.svg'.format(icon), class_name=class_name)


@app.template_filter('theme')
def _jinja2_filter_theme(b):
    theme = SETTINGS.get('theme')
    if theme is None:
        theme = 'default'
    return DB.get_theme_vars(theme)

@app.template_filter('theme_settings')
def _jinja2_filter_theme(b):
    return DB.get_settings_by_keys(['spacing', 'fs-base', 'rnd', 'icon', 'pfp-dim'])


@app.template_filter('dt')
def _jinja2_filter_datetime(ts):
    t = arrow.get(int(ts))
    return t.humanize()


@app.template_filter('decr')
def _jinja2_filter_decr(content, pubkey, privkey):
    try:
        k = bytes.fromhex(privkey)
        pk = PrivateKey(k)
        message = pk.decrypt_message(content, pubkey)
        if pubkey == SETTINGS.get('pubkey') and message[:19] == "::BIJA_CFG_BACKUP::":
            return "==================== BIJA CONFIG BACKUP. ====================<form class='cfg_loader'><input type='hidden' value='{}' name='cfg'><button>Click to reload settings</button></form>".format(message[19:])
        else:
            return strip_tags(message)
    except ValueError:
        return 'could not decrypt!'

@app.template_filter('nip05_valid')
def _jinja2_filter_nip5(nip5, validated):
    htm = "<span class='nip5' title='{}'>{}</span>"
    if nip5 is not None:
        if nip5[0:2] == "_@":
            nip5 = nip5[2:]
        if validated:
            status = 'verified'
        else:
            status = 'warn'
        nip5_htm = render_template('svg/{}.svg'.format(status), title=nip5, class_name='icon {}'.format(status))
        return htm.format(nip5, nip5_htm)
    return ''

@app.template_filter('ident_string')
def _jinja2_filter_ident(name, display_name, pk, long=True):
    html = "<span class='uname' data-pk='{}'><span class='name'>@{}</span></span> "
    if long:
        html = "<span class='long-name'><span class='uname' data-pk='{}'><span class='display_name'>{}</span><span class='name'>@{}</span></span></span>"

    if name is None or len(name.strip()) < 1:
        name = "{}&#8230;".format(pk[0:21])
    if long:
        if display_name is None:
            display_name = ''
        return html.format(pk, display_name, name)

    return html.format(pk, name)

@app.template_filter('relationship')
def _jinja2_filter_relate(pk):
    htm = '<span class="tag relationship">{}</span>'
    if pk == SETTINGS.get('pubkey'):
        return ''
    follows_me = DB.a_follows_b(pk, SETTINGS.get('pubkey'))
    i_follow = DB.a_follows_b(SETTINGS.get('pubkey'), pk)
    if follows_me and i_follow:
        return htm.format('you follow each other')
    elif follows_me:
        return htm.format('follows you')
    elif i_follow:
        return htm.format('following')
    else:
        return ''

@app.template_filter('responders_string')
def _jinja2_filter_responders(the_dict, n):
    names = []
    for pk, name in the_dict.items():
        names.append([pk, _jinja2_filter_ident(name, '', pk, long=False)])

    if n == 1:
        url = url_for('profile_page', pk=names[0][0])
        html = '<a href="{}">{}</a> commented '
        return html.format(url, names[0][1])
    elif n == 2:
        url1 = url_for('profile_page', pk=names[0][0])
        url2 = url_for('profile_page', pk=names[1][0])
        html = '<a href="{}">{}</a> and <a href="{}">{}</a> commented '
        return html.format(url1, names[0][1], url2, names[1][1])
    else:
        url1 = url_for('profile_page', pk=names[0][0])
        url2 = url_for('profile_page', pk=names[1][0])
        html = '<a href="{}">{}</a>, <a href="{}">{}</a> and {} others commented '
        return html.format(url1, names[0][1], url2, names[1][1], n - 2)

@app.template_filter('boosters_string')
def _jinja2_filter_boosters(the_dict, n):
    names = []
    for pk, name in the_dict.items() :
        names.append([pk, _jinja2_filter_ident(name, '', pk, long=False)])
    icon = _jinja2_filter_svg('reshare', 'icon-sm')
    if n == 1:
        url = url_for('profile_page', pk=names[0][0])
        html = '{} boosted by <a href="{}">{}</a> '
        return html.format(icon, url, names[0][1])
    elif n == 2:
        url1 = url_for('profile_page', pk=names[0][0])
        url2 = url_for('profile_page', pk=names[1][0])
        html = '{} boosted by <a href="{}">{}</a> and <a href="{}">{}</a> '
        return html.format(icon, url1, names[0][1], url2, names[1][1])
    else:
        url1 = url_for('profile_page', pk=names[0][0])
        url2 = url_for('profile_page', pk=names[1][0])
        html = '{} boosted by <a href="{}">{}</a>, <a href="{}">{}</a> and {} others'
        return html.format(icon, url1, names[0][1], url2, names[1][1], n - 2)

@app.template_filter('process_media_attachments')
def _jinja2_filter_media(json_string):
    a = json.loads(json_string)
    if len(a) > 0:
        media = a[0]
        if media[1] == 'image':
            n = 0
            ims_htm = ''
            ims_class = ''
            for m in a:
                if m[1] == 'image':
                    n += 1
                    ims_htm += '<span><img data-src="{}" data-srcset="{}" src="/static/blank.png" class="lazy-load" referrerpolicy="no-referrer"></span>'.format(m[0], m[0])
            if n == 2:
                ims_class = ' col2'
            elif n > 2 < 6:
                ims_class = ' col3'
            elif n >= 6:
                ims_class = ' col5'
            return '<div class="image-attachment{}">{}</div>'.format(ims_class, ims_htm)

        elif media[1] == 'og':
            return render_template("note.og.html", data=media[0])
        elif media[1] == 'video':
            return render_template("note.video.html", src=media[0], format=media[2])
        elif media[1] == "website":
            return render_template("note.og2.html", url=media[0])
    return ''


@app.template_filter('process_note_content')
def _jinja2_filter_note(content: str, limit=500):

    invoice = get_invoice(content.lower())
    if invoice is not None:
        data = construct_invoice(invoice.group())
        if data:
            invoice_html = render_template("ln.invoice.html", data=data)
            content = re.sub(invoice.group(), invoice_html, content, flags=re.IGNORECASE)
            limit = None

    if limit is not None and len(strip_tags(content)) > limit:

        content = textwrap.shorten(strip_tags(content), width=limit, break_long_words=True,
                                   placeholder="... <a href='#' class='read-more'>more</a>")

    hashtags = get_hash_tags(content)

    hashtags.sort(key=len, reverse=True)
    for tag in hashtags:
        term = tag[2:-1].strip()
        content = "{} ".format(content).replace(
            tag[:-1],
            "<a href='/topic?tag={}'>{}</a>".format(term, tag[:-1]))

    tags = get_at_tags(content)
    for tag in tags:
        pubkey = tag[1:]
        if is_bech32_key('npub', pubkey):
            pk = bech32_to_hex64('npub', pubkey)
        else:
            pk = pubkey
        if is_hex_key(pk):
            name = '{}&#8230;{}'.format(pk[:3], pk[-5:])
            profile = DB.get_profile(pk)
            if profile is not None and profile.name is not None and len(profile.name) > 0:
                name = profile.name
            content = content.replace(
                "@{}".format(pubkey),
                "<a class='uname' href='{}'>@{}</a>".format(url_for('profile_page', pk=pk), name))

    print(content)
    return content


def construct_invoice(content: str):
    try:
        out = {
            'sats': 0,
            'description': '',
            'date': '',
            'expires': '',
            'qr': '',
            'lnurl': content
        }
        content = content.split()
        invoice = lndecode(content[0])
        if invoice is not None:
            out['sats'] = str(int(invoice.amount * 100000000))
            out['date'] = str(invoice.date)
            for tag in invoice.tags:
                if tag[0] == 'd':
                    out['description'] = tag[1]
                if tag[0] == 'x':
                    out['expires'] = str(invoice.date + tag[1])
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(content[0])
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()
            img64 = base64.b64encode(img_byte_arr).decode()
            out['qr'] = '<img src="data:image/png;base64,{}">'.format(img64)
            return out
        return False
    except:
        return False

@app.template_filter('QR')
def _jinja2_filter_qr(string):
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(string)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        img64 = base64.b64encode(img_byte_arr).decode()
        out = '<img src="data:image/png;base64,{}">'.format(img64)
        return out
    except:
        return False

@app.template_filter('get_thread_root')
def _jinja2_filter_thread_root(root, reply, note_id):
    out = {'root': '', 'reply': ''}
    if root is None and reply is None:
        out['root'] = note_id
    else:
        out = {'root': root, 'reply': note_id}
    return out


@app.template_filter('linkify')
def _jinja2_filter_linkify(content):
    return url_linkify(content)


@app.template_filter('settings_json')
def _jinja2_settings_json(content):
    settings = ['cloudinary_cloud', 'cloudinary_upload_preset']
    out = {}
    for k in settings:
        v = SETTINGS.get(k)
        if v is not None:
            out[k] = v
    return json.dumps(out)
