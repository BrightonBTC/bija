import json
import textwrap

from flask import render_template
import arrow

from bija.app import app
from bija.db import BijaDB
from bija.helpers import get_at_tags, is_hex_key, url_linkify, strip_tags
from python_nostr.nostr.key import PrivateKey

DB = BijaDB(app.session)


@app.template_filter('dt')
def _jinja2_filter_datetime(ts):
    t = arrow.get(ts)
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
    if long:
        html = html + "<span class='nip5'>{}</span>"
    if validated and nip5 is not None and long:
        if nip5[0:2] == "_@":
            nip5 = nip5[2:]
        nip5 = nip5 + " <img src='/static/verified.svg' class='icon-sm'>"
    elif name is None or len(name.strip()) < 1:
        name = "{}&#8230;".format(pk[0:21])

    if long:
        if nip5 is None:
            nip5 = ""
        return html.format(pk, name, nip5)

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
def _jinja2_filter_note(content: str, limit=200):
    tags = get_at_tags(content)

    if limit is not None and len(strip_tags(content)) > limit:
        content = textwrap.shorten(strip_tags(content), width=limit, replace_whitespace=False, break_long_words=True,
                                   placeholder="... <a href='#' class='read-more'>more</a>")
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

