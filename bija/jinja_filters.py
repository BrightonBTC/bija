import base64
import io
import json
import logging
import re
import textwrap
import qrcode

from lightning.lnaddr import lndecode

from flask import render_template
import arrow

from bija.app import app
from bija.args import LOGGING_LEVEL
from bija.db import BijaDB
from bija.helpers import get_at_tags, is_hex_key, url_linkify, strip_tags, get_invoice, get_hash_tags
from bija.settings import Settings
from python_nostr.nostr.key import PrivateKey

DB = BijaDB(app.session)
logger = logging.getLogger(__name__)
logger.setLevel(LOGGING_LEVEL)


@app.template_filter('svg_icon')
def _jinja2_filter_svg(icon, class_name):
    return render_template('svg/{}.svg'.format(icon), class_name=class_name)


@app.template_filter('theme')
def _jinja2_filter_theme(b):
    theme = Settings.get('theme')
    if theme is None:
        theme = 'default'
    return DB.get_theme_vars(theme)


@app.template_filter('dt')
def _jinja2_filter_datetime(ts):
    t = arrow.get(int(ts))
    return t.humanize()


@app.template_filter('decr')
def _jinja2_filter_decr(content, pubkey, privkey):
    try:
        k = bytes.fromhex(privkey)
        pk = PrivateKey(k)
        return pk.decrypt_message(content, pubkey)
    except ValueError:
        return 'could not decrypt!'


@app.template_filter('ident_string')
def _jinja2_filter_ident(name, pk, nip5=None, validated=None, long=True):
    html = "<span class='uname' data-pk='{}'><span class='name'>{}</span> "
    nip5_htm = ""
    if long:
        html = "<span class='nip5' title='{}'>{}</span><span class='uname' data-pk='{}'><span class='name'>{}</span>"
    if nip5 is not None and long:
        if nip5[0:2] == "_@":
            nip5 = nip5[2:]
        if validated:
            status = 'verified'
        else:
            status = 'warn'
        #nip5 = " <img src='/static/{}.svg' class='icon-sm nip5-{}' title='{}'> ".format(status, status, nip5)
        nip5_htm = render_template('svg/{}.svg'.format(status), title=nip5, class_name='icon-sm {}'.format(status))
    elif name is None or len(name.strip()) < 1:
        name = "{}&#8230;".format(pk[0:21])

    if long:
        if nip5 is None:
            nip5 = ""
            nip5_htm = ""
        return html.format(nip5, nip5_htm, pk, name)

    return html.format(pk, name)


@app.template_filter('responders_string')
def _jinja2_filter_responders(the_dict, n):
    names = []
    for pk, name in the_dict.items():
        names.append([pk, _jinja2_filter_ident(name, pk, long=False)])

    if n == 1:
        html = '<a href="/profile?pk={}">@{}</a> commented'
        return html.format(names[0][0], names[0][1])
    elif n == 2:
        html = '<a href="/profile?pk={}">@{}</a> and <a href="/profile?pk={}">@{}</a> commented'
        return html.format(names[0][0], names[0][1], names[1][0], names[1][1])
    else:
        html = '<a href="/profile?pk={}">@{}</a>, <a href="/profile?pk={}">@{}</a> and {} other contacts commented'
        return html.format(names[0][0], names[0][1], names[1][0], names[1][1], n - 2)


@app.template_filter('process_media_attachments')
def _jinja2_filter_media(json_string):
    a = json.loads(json_string)
    if len(a) > 0:
        media = a[0]
        if media[1] == 'image':
            return '<div class="image-attachment"><img src="{}"></div>'.format(media[0])
        elif media[1] == 'og':
            return render_template("note.og.html", data=media[0])
        elif media[1] == 'video':
            return render_template("note.video.html", src=media[0], format=media[2])
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
        term = tag[1:].strip()
        content = "{} ".format(content).replace(
            tag,
            "<a href='/topic?tag={}'>{}</a> ".format(term, tag.strip())).strip()

    tags = get_at_tags(content)
    for tag in tags:
        pk = tag[1:]
        if is_hex_key(pk):
            name = '{}&#8230;{}'.format(pk[:3], pk[-5:])
            profile = DB.get_profile(pk)
            if profile is not None and profile.name is not None and len(profile.name) > 0:
                name = profile.name
            content = content.replace(
                "@{}".format(pk),
                "<a class='uname' href='/profile?pk={}'>@{}</a>".format(pk, name))
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
        v = Settings.get(k)
        if v is not None:
            out[k] = v
    return json.dumps(out)
