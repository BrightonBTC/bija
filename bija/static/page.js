function SOCK() {

    var socket = io.connect();
    socket.on('connect', function() {
        socket.emit('new_connect', {data: true});
    });
    socket.on('message', function(data) {
        updateMessageThread(data);
    });
    socket.on('unseen_messages_n', function(data) {
        let el_unseen = document.getElementById("n_unseen_messages");
        if(parseInt(data) == 0){
            el_unseen.style.display = "none";
        }
        else{
            el_unseen.style.display = "inline-block";
            el_unseen.innerText = data;
        }
    });
    socket.on('unseen_in_topics', function(data) {
        for(const [k, v] of Object.entries(data)){
            updateUnseenTopicCount(k, v)
        }
    });

    socket.on('unseen_posts_n', function(data) {
        let el_unseen = document.getElementById("n_unseen_posts");
        if(parseInt(data) == 0){
            el_unseen.style.display = "none";
        }
        else{
            el_unseen.style.display = "inline-block";
            el_unseen.innerText = data;
        }
    });
    socket.on('alert_n', function(data) {
        let el_unseen = document.getElementById("n_alerts");
        if(parseInt(data) == 0){
            el_unseen.style.display = "none";
        }
        else{
            el_unseen.style.display = "inline-block";
            el_unseen.innerText = data;
        }
    });

    socket.on('profile_update', function(data) {
        updateProfile(data);
    });
    socket.on('new_profile_posts', function(ts) {
        notifyNewProfilePosts(ts);
    });
    socket.on('new_in_thread', function(id) {
        document.dispatchEvent(new CustomEvent("newNote", {
            detail: { id: id }
        }));
    });
    socket.on('new_in_topic', function(id) {
        document.dispatchEvent(new CustomEvent("newTopicNote"));
    });

    socket.on('conn_status', function(data) {
        const connections = {'connected': 0, 'recent': 0, 'disconnected': 0, 'none':0};
        for(const relay in data){
            r = data[relay];
            let urel = document.querySelector(".relay[data-url='"+r[0]+"'] .led");
            if(r[1] == null){
                connections.none += 1;
                if(urel){
                    urel.setAttribute("class", "led none");
                }
            }
            else if(parseInt(r[1]) < 60){
                connections.connected += 1;
                if(urel){
                    urel.setAttribute("class", "led connected");
                }
            }
            else if(parseInt(r[1]) < 180){
                connections.recent += 1;
                if(urel){
                    urel.setAttribute("class", "led recent");
                }
            }
            else{
                connections.disconnected += 1;
                if(urel){
                    urel.setAttribute("class", "led disconnected");
                }
            }
        }
        const el = document.querySelector(".conn-status");
        el.innerHTML = "";
        for (const [k, v] of Object.entries(connections)) {
            if(v > 0){
                let span = document.createElement('span');
                span.classList.add('status');
                let span2 = document.createElement('span');
                span2.classList.add('led', k);
                let span3 = document.createElement('span');
                span3.innerText = v;
                span.append(span2);
                span.append(span3);
                el.append(span);
            }
        }
    });
    socket.on('new_note', function(note_id) {
        replaceNotePlaceholder(note_id);
    });
    socket.on('new_reaction', function(note_id) {
        updateInteractionCount(note_id, '.likes');
    });
    socket.on('new_reply', function(note_id) {
        updateInteractionCount(note_id, '.reply-n');
    });
    socket.on('new_reshare', function(note_id) {
        updateInteractionCount(note_id, '.quote-n');
    });
    socket.on('events_processing', function(event) {
        const elem = document.querySelector('.queued_count')
        if(event > 0){
            elem.innerText = 'Processing '+event+' queued events'
            elem.classList.add('fadeIn')
            elem.classList.remove('fadeOut')
        }
        else{
            elem.classList.add('fadeOut')
            elem.classList.remove('fadeIn')
        }
    });
}

let updateUnseenTopicCount = function(tag, n){
    const container_el = document.querySelector('ul.topic-list li[data-tag="'+tag+'"]')
    if(container_el){
        n_el = container_el.querySelector('.unseen_n')
        if(n > 0){
            n_el.innerHTML = '<span>'+n+'</span>'
        }
        else{
            n_el.innerHTML= ''
        }
    }
}

let replaceNotePlaceholder = function(id){
    const ph_els = document.querySelectorAll('.note-container.placeholder[data-id="'+id+'"]')
    const cb = function(response, data){
        if(response){
            const doc = new DOMParser().parseFromString(response, "text/html")
            const new_item = doc.body.firstChild
            for (const el of data.els) {
                el.replaceWith(new_item)
            }
            document.dispatchEvent(new Event('newContentLoaded'))
        }
    }
    if(ph_els.length > 0){
        fetchGet('/thread_item?id='+id, cb, {'els': ph_els})
    }
}

let updateInteractionCount = function(note_id, cls){
    const note_el = document.querySelector('.note[data-id="'+note_id+'"]');
    if(note_el){
        like_el = note_el.querySelector(cls);
        if(like_el){
            n = like_el.innerText.trim()
            if(n.length < 1) n = 0;
            like_el.innerText = parseInt(n) + 1
        }
    }
}

let notifyNewProfilePosts = function(ts){
    first_note = document.querySelector('#profile-posts[data-latest]');
    if(first_note){
        latest = first_note.dataset.latest;
    }
    else{
        latest = 0;
    }
    if(ts > latest){
        elem = document.querySelector("#profile-posts");
        notifications = document.querySelectorAll(".new-posts");
        if(elem && notifications.length < 1){
            notification = document.createElement('a');
            notification.innerText = 'Show new posts';
            notification.href = ''
            notification.classList.add('new-posts')
            elem.prepend(notification)
        }
    }
}
let updateProfile = function(profile){
    document.querySelector(".profile-about").innerHTML = profile.about
    document.querySelector("#profile").dataset.updated_ts = profile.updated_at
    const name_els = document.querySelectorAll(".uname[data-pk='"+profile.public_key+"']");
    for (const name_el of name_els) {

        if(profile.name != null && profile.name.length > 0){
            const nm = name_el.querySelector('.name')
            if(nm){
                nm.innerText = profile.name
            }
        }
        if(profile.nip05 != null && profile.nip05.length > 0 && profile.nip05_validated){
            const nip5 = name_el.querySelector('.nip5')
            if(nip5){
                nip5.innerText = profile.nip05
            }
        }
    }
    const pic_els = document.querySelectorAll(".user-image[data-rel='"+profile.public_key+"']");
    for (const pic_el of pic_els) {
        pic_el.setAttribute("src", profile.pic)
    }
}

let updateMessageThread = function(data){
    const messages_elem = document.querySelector("#messages_from")
    if(messages_elem){
        let shouldScroll = false
        if ((window.innerHeight + Math.ceil(window.pageYOffset)) >= document.body.offsetHeight) {
           shouldScroll = true
        }
        messages_elem.innerHTML += data
        if(shouldScroll){
            window.scrollTo(0, document.body.scrollHeight);
        }
        else{
            notify('new messages')
        }
    }
}

class bijaSearch{
    constructor(){
        this.setEventListeners()
    }

    setEventListeners(){
        const search = document.querySelector('input[name="search_term"]');
        search.addEventListener("keyup", (event)=>{
            document.querySelector('#search_hints').innerHTML = ''
            const val = search.value
            if (val.substring(0, 1) == '@'){
                this.searchByName(val.substring(1))
            }
        })
        this.searchTipsFill()
        search.addEventListener("focus", (event)=>{
            document.querySelector('#search_tips').style.display = 'block'
        })
        search.addEventListener("blur", (event)=>{
            document.querySelector('#search_tips').style.display = 'none'
        })
    }

    searchByName(name){
        const cb = function(response, data){
            if(response['result']){
                console.log(data)
                data.context.showNameHints(response['result'], data.search)
            }
        }
        fetchGet('/search_name?name='+name, cb, {
            'context':this,
            'search':name
        }, 'json')
    }

    showNameHints(results, search_str){
        const reply_elem = document.querySelector('input[name="search_term"]')
        const hint_elem = document.querySelector('#search_hints')
        if(results.length > 0){
            const ul = document.createElement('ul')
            ul.classList.add('hint-list')
            for(const name of results) {
                let li = document.createElement('li')
                if(!name['name'] || name['name'].length < 1){
                    name['name'] = name['public_key']
                }
                li.innerText = name['name']
                li.addEventListener("click", (event)=>{
                    reply_elem.value = reply_elem.value.replace('@'+search_str, '@'+name['name'])
                    reply_elem.parentElement.submit();
                });
                ul.append(li)
            }
            hint_elem.append(ul)
        }
    }
    
    searchTipsFill() {
        const reply_elem = document.querySelector('input[name="search_term"]')
        const tips_elems = document.querySelectorAll('#search_tips > li')
        let fill_contents = Array.from(tips_elems).map(li => li.getAttribute('data-fill'))
        tips_elems.forEach(elem => {
            elem.addEventListener('mousedown', (event) => {
                event.preventDefault()
            }); 
            elem.addEventListener("click", (event) => {
                let fill_content = elem.getAttribute('data-fill')
                if (fill_content.length > 0) {
                    if (fill_contents.includes(reply_elem.value[0])) {
                        reply_elem.value = reply_elem.value.replace(reply_elem.value[0], fill_content)
                    } else {
                        reply_elem.value = fill_content + reply_elem.value
                    }
                } else {
                    reply_elem.value = ''
                }
                reply_elem.blur()
                reply_elem.focus()
            })
        })
    }
}

// tools common to all post forms (new note, reply, quote...)
class bijaNoteTools{
    constructor(){
        this.setEventListeners()
        document.addEventListener('newContentLoaded', ()=>{
            this.setEventListeners()
        });
        document.addEventListener('quoteFormLoaded', ()=>{
            this.setEventListeners()
        });
    }

    setEventListeners(){
        const reply_els = document.querySelectorAll('textarea.note-textarea');
        for(const reply_el of reply_els){
            if(!reply_el.dataset.toolset){
                reply_el.dataset.toolset = true
                this.setNameHintFetch(reply_el)
            }
        }
    }

    setNameHintFetch(reply_el){
        reply_el.addEventListener("keyup", (event)=>{
            const hint_elem = reply_el.parentElement.querySelector('.name-hints')
            hint_elem.innerHTML = ''
            const matches = match_mentions(reply_el.value);
            if(matches){
                let name = false
                for(const match of matches){
                    const match_pos = reply_el.value.search(match)+match.length
                    if(match_pos == reply_el.selectionEnd){
                        name = match.substring(1);
                        break;
                    }
                }
                if(name){
                    const cb = function(response, data){
                        if(response['result']){
                            console.log(data)
                            data.context.showNameHints(data.hint_elem, data.reply_elem, response['result'], data.search)
                        }
                    }
                    fetchGet('/search_name?name='+name, cb, {
                        'context':this,
                        'hint_elem':hint_elem,
                        'reply_elem':reply_el,
                        'search':name
                    }, 'json')
                }
            }

        });
    }

    showNameHints(hint_elem, reply_elem, results, search_str){
        if(results.length > 0){
            const ul = document.createElement('ul')
            ul.classList.add('hint-list')
            for(const name of results) {
                let li = document.createElement('li')
                if(!name['name'] || name['name'].length < 1){
                    name['name'] = name['public_key']
                }
                li.innerText = name['name']
                li.addEventListener("click", (event)=>{
                    reply_elem.value = reply_elem.value.replace('@'+search_str, '@'+name['name'])
                    reply_elem.selectionStart=reply_elem.value.length;
                    reply_elem.focus();
                    hint_elem.innerHTML = ''
                });
                ul.append(li)
            }
            hint_elem.append(ul)
        }
    }
}

class bijaNotePoster{
    constructor(){
        this.setEventListeners();
    }

    setEventListeners(){
        const btn = document.querySelector('#new_post_submit');
        const form = document.querySelector('#new_post_form');

        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const cb = function(response, data){
                if(response['event_id']){
                    window.location.href = '/note?id='+response['event_id']
                }
            }
            fetchFromForm('/submit_note', form, cb, {}, 'json');
        });
    }
}

class bijaSettings{
    constructor(){
        this.setEventListeners();
    }

    setEventListeners(){

        this.setPrivateKeyReveal()
        this.setUpdateConnsClickedEvent()

        this.setRelayRemoveClickedEvents()

        this.setDeleteKeysClicked()

        const relay_btn = document.querySelector("#addrelay");
        relay_btn.addEventListener("click", (event)=>{
            event.preventDefault();
            event.stopPropagation();
            const form = document.querySelector("#relay_adder")

            const cb = function(response, data){
                data.context.reloadRelayList()
            }
            fetchFromForm('/add_relay', form, cb, {'context': this})
        });

        const cld_btn = document.querySelector("#upd_cloudinary");
        cld_btn.addEventListener("click", (event)=>{
            event.preventDefault();
            event.stopPropagation();
            const form = document.querySelector("#cloudinary_cfg")

            const cb = function(response, data){
                notify('updated')
            }
            fetchFromForm('/update_settings', form, cb, {}, 'json')
        });

        const pow_btn = document.querySelector("#upd_pow");
        pow_btn.addEventListener("click", (event)=>{
            event.preventDefault();
            event.stopPropagation();
            const pow_form = document.querySelector("#pow_cfg")

            const pow_cb = function(response, data){
                notify('updated')
            }
            fetchFromForm('/update_settings', pow_form, pow_cb, {}, 'json')
        });

        const theme_form = document.querySelector("#theme_form");
        const theme_select = theme_form.querySelector("select");
        theme_select.addEventListener("change", (event)=>{

            const theme_cb = function(response, data){
                location.reload();
            }
            fetchFromForm('/update_settings', theme_form, theme_cb, {}, 'json')
        });

    }

    setDeleteKeysClicked(){
        const btn = document.querySelector('#del_keys')
        btn.addEventListener("click", (event)=>{
            event.preventDefault();
            event.stopPropagation();
            const container = document.createElement('div')
            const txt = document.createElement('p')
            const btn = document.createElement('input')
            btn.setAttribute('type', 'button')
            btn.setAttribute('value', 'confirm')
            txt.innerText = "This action is irreversible! Make sure you've backed up your private key if you intend to access this account in the future. Clicking confirm below will completey remove all your data";
            container.append(txt)
            container.append(btn)
            popup('')
            document.querySelector('.popup').append(container)
            btn.addEventListener("click", (event)=>{
                window.location.href = '/destroy_account'
            })
        });
    }

    setPrivateKeyReveal(){
        const key_el = document.querySelector('.privkey')
        const reveal = document.querySelector('.show-key')
        const im = reveal.querySelector('img')
        reveal.addEventListener("click", (event)=>{
            if(key_el.classList.contains('show')){
                key_el.classList.remove('show')
                im.src = '/static/eye.svg'
            }
            else{
                key_el.classList.add('show')
                im.src = '/static/eye-off.svg'
                const cb = function(response, data){
                    data.elem.innerHTML = response
                    const reveal_btn = document.querySelector('button.reveal_pk')
                    const reveal_form = document.querySelector('#reveal_pk')
                    reveal_btn.addEventListener("click", (event)=>{
                        event.preventDefault();
                        event.stopPropagation();
                        const cb = function(response, data){
                            data.elem.innerHTML = response
                        }
                        const form = document.querySelector("#new_message_form")
                        fetchFromForm('/get_privkey', reveal_form, cb, {'elem':data.elem})
                    })
                }
                fetchGet('/get_privkey', cb, {'elem': key_el})

            }
        });
    }

    setRelayRemoveClickedEvents(){
        const relays = document.querySelectorAll(".relay[data-url]");
        for (const relay of relays) {
            this.setRelayRemoveClickedEvent(relay)
        }
    }

    setRelayRemoveClickedEvent(elem){
        elem.querySelector(".del-relay").addEventListener("click", (event)=>{
            const cb = function(response, data){
                data.context.reloadRelayList()
            }
            fetchGet('/del_relay?url='+elem.dataset.url, cb, {'context': this})
        });
    }

    setUpdateConnsClickedEvent(){
        const elem = document.querySelector(".refresh_connections");
        elem.addEventListener("click", (event)=>{
            const cb = function(response, data){
                data.context.reloadRelayList()
            }
            fetchGet('/refresh_connections', cb, {'context': this})
        });
    }

    reloadRelayList(){
        const cb = function(response, data){
            const doc = new DOMParser().parseFromString(response, "text/html")
            document.querySelector('#relays_list').innerHTML = ''
            document.querySelector('#relays_list').append(doc.body.firstChild)
            data.context.setRelayRemoveClickedEvents()
        }
        fetchGet('/reload_relay_list', cb, {'context': this})
    }
}

class bijaThread{

    constructor(){
        this.root = false;
        this.focussed = false;
        this.replies = [];
        document.addEventListener("newNote", (event)=>{
            const el = document.querySelector(".note-container[data-id='"+event.detail.id+"']")

            if( (el && el.classList.contains('placeholder')) || !el){

                fetchGet('/thread_item?id='+event.detail.id, this.processNewNoteInThread, {'elem': el, 'context':this})

            }
        });
    }

    processNewNoteInThread(response, data){
        const doc = new DOMParser().parseFromString(response, "text/html")
        const new_item = doc.body.firstChild
        if(!data.elem){
            const focussed_elem = document.querySelector(".note-container.main")
            if(focussed_elem){
                const focussed_id = focussed_elem.dataset.id
                if(new_item.dataset.parent == focussed_id){
                    document.querySelector('#thread-items').append(new_item)
                    new_item.classList.add('reply')
                }
            }
            document.dispatchEvent(new Event('newContentLoaded'))
        }
        else{
            console.log('replace elem')
            data.elem.replaceWith(new_item)
            document.dispatchEvent(new Event('newContentLoaded'))
        }
    }
}

class bijaMessages{
    constructor(){
        window.scrollTo(0, document.body.scrollHeight);
        this.setSubmitMessage()
    }

    setSubmitMessage(){
        document.querySelector('#new_message_submit').addEventListener("click", (event)=>{
            event.preventDefault();
            event.stopPropagation();
            this.postMessage()
            return false
        });
        document.querySelector('#new_message').addEventListener("keyup", (event)=>{
            if(event.which === 13){
                this.postMessage()
            }
        });

    }
    postMessage(){
        const cb = function(response, data){
            if(response['event_id']){
               window.scrollTo(0, document.body.scrollHeight);
               notify('Message sent')
               document.querySelector("#new_message").value = ''
           }
        }
        const form = document.querySelector("#new_message_form")
        fetchFromForm('/submit_message', form, cb, {}, 'json')
    }
}

class bijaProfile{

    constructor(){
        this.setEventListeners()
    }

    setEventListeners(){
        const btns = document.querySelectorAll(".follow-btn");
        for (const btn of btns) {
            btn.addEventListener("click", (event)=>{
                event.preventDefault();
                event.stopPropagation();
                let id = btn.dataset.rel;
                let state = btn.dataset.state;
                let upd = btn.dataset.upd;
                this.setFollowState(id, state, upd);
                return false;
            });
        }
        const edit_tog = document.querySelector(".profile-edit-btn");
        if(edit_tog){
            edit_tog.addEventListener("click", (event)=>{
                event.preventDefault();
                event.stopPropagation();
                const pel = document.querySelector("#profile");
                if(pel.classList.contains('editing')){
                    pel.classList.remove('editing')
                }
                else{
                    pel.classList.add('editing')
                }
            });
            const profile_updater = document.querySelector("#pupd");
            profile_updater.addEventListener("click", (event)=>{
                event.preventDefault();
                event.stopPropagation();

                const form = document.querySelector("#profile_updater")
                fetchFromForm('/upd_profile', form, this.updateProfile, {}, 'json')
            });

            const main_el = document.querySelector('.main')
            if(main_el && main_el.dataset.settings){
                const settings = JSON.parse(main_el.dataset.settings)
                if(settings['cloudinary_cloud'] !== undefined){
                    const form = document.querySelector("#profile_updater");
                    const im_up = document.querySelector(".profile-img-up");
                    im_up.addEventListener('change', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        uploadToCloud(form, function(data, elem){
                            const d = JSON.parse(data)
                            elem.querySelector('#pim').value = d.secure_url
                            elem.querySelector('.user-image').src = d.secure_url
                        })
                    });
                }
            }
        }
        const invalid_nip5 = document.querySelector('#profile .warn')
        if(invalid_nip5){
            this.setNip5Validator()
        }
    }

    setNip5Validator(){
        const pel = document.querySelector('#profile')
        const btn = document.createElement('button')
        btn.innerText = 'Revalidate Nip-05'
        const cb = function(response, data){
            if(response.valid==true){
                location.reload();
            }
            else{
                notify('Nip05 identifier could not be validated')
            }
        }
        btn.addEventListener('click', (e) => {
            fetchGet('/validate_nip5?pk='+pel.dataset.pk, cb, {}, 'json')
        });
        const name_el = pel.querySelector('.profile-name')
        name_el.append(btn)
    }

    updateProfile(response, data){
        if(response['success']){
            notify('Profile updated')
            document.querySelector("#nip5").classList.remove('error')
        }
        else if(response['nip05'] === false){
            notify('Nip05 identifier could not be validated')
            document.querySelector("#nip5").classList.add('error')
        }
        else{
            notify('Something went wrong updating your profile. Check for any errors and try again.')
        }
    }

    setFollowState(id, state, upd){
        const cb = function(response, data){
            if(data.upd == '1'){
                document.querySelector(".profile-tools").innerHTML = response
            }
            else{
                const f_btn = document.createElement('img')
                f_btn.classList.add('icon')
                f_btn.src = '/static/following.svg'
                const c_btn = document.querySelector(".follow-btn[data-rel='"+data.id+"']")
                c_btn.replaceWith(f_btn)
            }
        }
        fetchGet('/follow?id='+id+"&state="+state+"&upd="+upd, cb, {'upd':upd,'id':id})
    }

}

class bijaNotes{
    constructor(){
        this.setEventListeners()
        document.addEventListener('newContentLoaded', ()=>{
            this.setEventListeners()
        });
        setInterval(this.tsUpdater, 120000);
    }

    tsUpdater(){
        console.log('update ts')
        const notes = document.querySelectorAll(".dt[data-ts]");
        const timestamps = []
        for (const n of notes) {
            timestamps.push(n.dataset.ts)
        }
        const cb = function(response, data){
            const stamps = JSON.parse(response)
            console.log(stamps)
            for (const [k, v] of Object.entries(stamps['data'])) {
                const elem = document.querySelector(".dt[data-ts='"+k+"']");
                if(elem){
                    elem.innerText = v
                }
            }
        }
        if(timestamps.length > 0){
            fetchGet('/timestamp_upd?ts='+timestamps.join(), cb)
        }
    }

    setEventListeners(){
        const notes = document.querySelectorAll(".note[data-processed='0']");
        const main_el = document.querySelector('.main')
        for (const note of notes) {
            note.dataset.processed = '1'

            const link = note.querySelector(".reply-link");
            if(link){
                this.setReplyLinkEvents(link)
            }

            const btn = note.querySelector("input[data-reply-submit]");
            if(btn){
                this.setReplyClickedEvents(btn)
            }

            const note_link = note.querySelector(".note-content[data-rel]");
            this.setContentClickedEvents(note_link)

            const opt_el = note.querySelector(".note-opts");
            this.setOptsMenuEvents(opt_el)

            const q_el = note.querySelector(".quote-link");
            if(q_el){
                this.setQuoteClickedEvents(q_el)
            }

            const like_el = note.querySelector("a.like");
            if(like_el){
                this.setLikeClickedEvents(like_el)
            }

            const im_el = note.querySelector(".image-attachment img");
            if(im_el){
                this.setImageClickEvents(im_el)
            }

            const like_n_el = note.querySelector(".likes.counts");
            if(like_n_el){
                this.setLikeCountClickEvents(like_n_el, note.dataset.id)
            }
            const settings = JSON.parse(main_el.dataset.settings)
            if(settings['cloudinary_cloud'] !== undefined){
                const upload_form = note.querySelector('.reply-form')
                setCloudUploads(upload_form)
            }
            const emoji_link = note.querySelector(".emojis");
            if(emoji_link){
                new Emojis(note)
            }
            const read_more_link = note.querySelector(".read-more");
            if(read_more_link){
                this.setReadMoreClicks(read_more_link, note.dataset.id)
            }

            const qr_btn = note.querySelector(".qr_show");
            if(qr_btn){
                this.setQrToggle(qr_btn, note.dataset.id)
            }

            const ct = note.querySelector('.poster-form textarea');
            if(ct){
                ct.addEventListener('focus', (e) => {
                ct.classList.add('focus')
                ct.classList.remove('blur')
                });
                ct.addEventListener('blur', (e) => {
                    setTimeout(function(){
                        ct.classList.remove('focus')
                        ct.classList.add('blur')
                    }, 1000)
                });
            }

        }
    }

    setQrToggle(elem, id){
        elem.addEventListener('click', (e) => {
            event.stopPropagation();
            const note_el = document.querySelector('.note[data-id="'+id+'"]')
            const invoice_el = note_el.querySelector('.ln_invoice')
            if(invoice_el.classList.contains('qr_show')){
                invoice_el.classList.remove('qr_show')
            }
            else{
                invoice_el.classList.add('qr_show')
            }
        })
    }

    setReadMoreClicks(elem, id){
        elem.addEventListener('click', (e) => {
            event.preventDefault();
            event.stopPropagation();

            const cb = function(response, data){
                if(response != '0'){
                    const note_el = document.querySelector('.note[data-id="'+data.id+'"]')
                    const content_el = note_el.querySelector('.note-content pre')
                    content_el.innerHTML = response
                }
            }
            fetchGet('/read_more?id='+id, cb, {'id': id})
        })
    }

    setImageClickEvents(elem){
        elem.addEventListener("click", (event)=>{
            const im = elem.parentElement.innerHTML
            popup(im)
        });
    }

    
    setReplyClickedEvents(elem){
        elem.addEventListener("click", (event)=>{
            event.preventDefault();
            event.stopPropagation();
            this.postReply(elem.dataset.rel)
        });
    }

    setLikeClickedEvents(elem){
        elem.addEventListener('click', (e) => {
            event.preventDefault();
            event.stopPropagation();
            const d = elem.dataset
            if(d.disabled == true) return
            d.disabled = true
            if(d.liked == 'True'){
                d.liked = 'False'
            }
            else{
                d.liked = 'True'
            }
            const cb = function(response, data){
                data.elem.dataset.disabled = false
                const doc = new DOMParser().parseFromString(response, "text/html")
                const svg = doc.body.firstChild
                elem.replaceWith(svg)
                document.dispatchEvent(new Event('newContentLoaded'))
            }
            fetchGet('/like?id='+d.rel, cb, {'elem': elem})
        })
    }

    setContentClickedEvents(elem){
        elem.querySelector('pre').addEventListener("click", (event)=>{
            let id = elem.dataset.id
            const container_el = document.querySelector(".note-container[data-id='"+id+"']");
            if(container_el && container_el.classList.contains("main")){

            }
            else{
                event.preventDefault();
                event.stopPropagation();
                let rel = elem.dataset.rel
                window.location.href = '/note?id='+id+'#focussed'
            }
        });
        const links = elem.querySelectorAll('pre a')
        for(const link of links){
            link.addEventListener("click", (event)=>{
                event.stopPropagation();
            });
        }
    }

    setReplyLinkEvents(elem){
        elem.addEventListener("click", (event)=>{
            event.preventDefault();
            event.stopPropagation();
            const event_id = elem.dataset.rel
            const form_el = document.querySelector(".reply-form[data-noteid='"+event_id+"']")
            if (form_el.dataset.vis == '1'){
                form_el.dataset.vis = '0'
                form_el.style.display = "none"
            }
            else{
                form_el.dataset.vis = '1'
                form_el.style.display = "flex"
            }
        });
    }

    setQuoteClickedEvents(elem){
        elem.addEventListener('click', (e) => {
            event.preventDefault();
            event.stopPropagation();
            const note_id = elem.dataset.rel
            const cb = function(response, data){
                if(response){
                    popup(response)
                    data.context.setQuoteForm()
                }
            }
            fetchGet('/quote_form?id='+note_id, cb, {'context': this})
        })
    }

    setOptsMenuEvents(elem){
        const note_id = elem.dataset.id
        const tools = elem.querySelectorAll('.opts-menu li')
        for (const tool_el of tools) {
            const tool  = tool_el.dataset.action;
            if(tool == 'nfo'){
                tool_el.addEventListener('click', (e) => {
                    event.preventDefault();
                    event.stopPropagation();
                    const on_get_info = function(response, data){
                        if(response['data']){
                            popup("<pre>"+JSON.stringify(JSON.parse(response['data']), null, 2)+"</pre>")
                        }
                    }
                    fetchGet('/fetch_raw?id='+note_id, on_get_info, {}, 'json')
                })
            }
            else if(tool == 'del'){
                tool_el.addEventListener('click', (e) => {
                    event.preventDefault();
                    event.stopPropagation();
                    const on_req_delete_confirm = function(response, data){
                        if(response){
                            popup(response)
                            data.context.setDeleteForm()
                        }
                    }
                    fetchGet('/confirm_delete?id='+note_id, on_req_delete_confirm, {context:this})
                })
            }
        }
    }

    setLikeCountClickEvents(elem, id){
        elem.addEventListener('click', (e) => {
            const cb = function(response, data){
                console.log(response)
                popup('')
                data.context.displayReactionDetails(response.data)

            }
            fetchGet('/get_reactions?id='+id, cb, {'context': this}, 'json')
        });
    }

    displayReactionDetails(response){
        const container = document.createElement('ul')
        container.classList.add('liked_by')
        for (var i = 0; i < response.length; i++){
            let li = document.createElement('li')
            if(response[i].content == null || response[i].content.length < 1 || response[i].content == "+"){
                response[i].content = "🤍"
            }
            if(response[i].name == null || response[i].name.length < 1){
                response[i].name = response[i].public_key.substring(0, 21)+"..."
            }

            li.innerHTML = '<span>'+response[i].content+'</span><a href="/profile?pk='+response[i].public_key+'">'+response[i].name+'</a>';
            container.append(li)
        }
        const p = document.querySelector('.popup')
        p.append(container)
    }

    setDeleteForm(){
        const form = document.querySelector("#delete_form")
        const btn = form.querySelector("input[type='submit']")
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const cb = function(response, data){
                if(response['event_id']){
                   notify('Note deleted')
                }
            }
            fetchFromForm('/delete_note', form, cb, {}, 'json')
        });
    }

    setQuoteForm(){
        const form = document.querySelector("#quote_form")
        const btn = form.querySelector("input[type='submit']")
        document.dispatchEvent(new Event('quoteFormLoaded'))
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const cb = function(response, data){
                if(response['event_id']){
                    window.location.href = '/note?id='+response['event_id']+'#'+response['event_id']
//                   notify('Note created. View now?', '/note?id='+response['event_id']+'#'+response['event_id'])
                }
            }
            fetchFromForm('/quote', form, cb, {}, 'json')
        });
    }

    postReply(id){
        const form = document.querySelector(".reply-form[data-noteid='"+id+"']")
        const cb = function(response, data){
            if(response['event_id']){
                window.location.href = '/note?u='+Date.now()+'&id='+response['event_id']
//                notify('Note created. View now?', '/note?id='+response['root']+'#'+response['event_id'])
                data.form.dataset.vis = '0'
                data.form.style.display = "none"
            }
        }
        fetchFromForm('/submit_note', form, cb, {'form':form}, 'json')
    }
}

class bijaFeed{

    constructor(){
        const main_el = document.querySelector(".main[data-page]")
        if(main_el.dataset.page=='home'){
            new Emojis(main_el.querySelector('#note-poster'))
        }

        const ct = document.querySelector('#new_post');
        if(ct){
            ct.addEventListener('focus', (e) => {
            ct.classList.add('focus')
            ct.classList.remove('blur')
            });
            ct.addEventListener('blur', (e) => {
                setTimeout(function(){
                    ct.classList.remove('focus')
                    ct.classList.add('blur')
                }, 1000)
            });
        }

        this.page = main_el.dataset.page
        this.data = {};
        this.loading = 0;
        this.listener = () => this.loader(this);
        window.addEventListener('scroll', this.listener);
        this.pageLoadedEvent = new Event("newContentLoaded");
    }

    loader(o){
        if ((window.innerHeight + window.innerHeight + window.scrollY) >= document.body.offsetHeight && o.loading == 0){
            let nodes = document.querySelectorAll('.ts[data-ts]')
            let ts = Math.floor(Date.now() / 1000)
            if(nodes.length > 0){
                ts = nodes[nodes.length-1].dataset.ts
            }
            o.requestNextPage(ts);
        }
    }

    setLoadingCompleted(){
        this.loading = 2; // nothing more to load
    }

    requestNextPage(ts){
        this.loading = 1;
        const cb = function(response, data){
            if(response == 'END'){
                data.context.loading = 3
            }
            else{
                data.context.loadArticles(response);
                document.dispatchEvent(data.context.pageLoadedEvent);
            }
        }
        if(this.page == 'home'){
            fetchGet('/feed?before='+ts, cb, {'context': this})
        }
        else if(['profile', 'profile-me'].includes(this.page)){
            const profile_elem = document.querySelector("#profile")
            fetchGet('/profile_feed?before='+ts+'&pk='+profile_elem.dataset.pk, cb, {'context': this})
        }
        else if(this.page == 'topic'){
            const topic_elem = document.querySelector(".topic-sub")
            fetchGet('/topic_feed?before='+ts+'&topic='+topic_elem.dataset.topic, cb, {'context': this})
        }
    }

    loadArticles(response){
        const doc = new DOMParser().parseFromString(response, "text/html")
        const htm = doc.body.firstChild
        document.getElementById("main-content").append(htm);
        const o = this
        setTimeout(function(){
            o.loading = 0;
			lazyLoad();
        }, 200)
    }
}

class bijaTopic{

    constructor(){
        const subscribe_el = document.querySelector(".topic-sub")
        subscribe_el.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const cb = function(response, data){
                subscribe_el.dataset.state = response.state
                subscribe_el.innerText = response.label
            }
            fetchGet('/subscribe_topic?state='+subscribe_el.dataset.state+'&topic='+subscribe_el.dataset.topic, cb, {}, 'json')
        });

        const t_btn = document.querySelector('#new_topic_posts_btn')
        t_btn.addEventListener("click", (event)=>{
            location.reload()
        });
        document.addEventListener("newTopicNote", (event)=>{
            t_btn.style.display = 'block'
        });
    }
}

class Emojis{
    constructor(target_el){
        this.target_el = target_el
        this.search_el = target_el.querySelector('.emoji_selector input')
        this.trigger_btn = target_el.querySelector('.emojis')
        this.emoji_container = target_el.querySelector('.emoji_selector')
        this.emoji_div = target_el.querySelector('.emoji_selector div')
        this.textarea = target_el.querySelector('.poster-form textarea')

        this.setEventsListeners()
    }
    setEventsListeners(){
        this.textarea.addEventListener("keydown", (event)=>{
            this.closeEmojisContainer()
        });
        this.trigger_btn.addEventListener("click", (event)=>{
            let is_showed = this.emoji_container.classList.contains('show')
            if (is_showed) {
                this.closeEmojisContainer()
            } else {
                fetchGet('/emojis', this.loadEmojis, {'context': this}, 'json')
            }
        });
        this.search_el.addEventListener("keyup", (event)=>{
            fetchGet('/emojis?s='+this.search_el.value, this.loadEmojis, {'context': this}, 'json')
        });
    }
    loadEmojis(response, data){
        if(response){
            data.context.emoji_div.innerHTML = ""
            data.context.emoji_container.classList.add('show')

            for(const item of response.emojis){
                const a = document.createElement('a')
                a.href = '#'
                a.innerText = item
                a.addEventListener("click", (event)=>{
                    event.stopPropagation();
                    event.preventDefault();
                    data.context.textarea.value += a.innerText
                    data.context.search_el.value = ''
                    fetchGet('/emojis', data.context.loadEmojis, {'context': data.context}, 'json')
                });
                data.context.emoji_div.append(a)
            }
        }
    }
    closeEmojisContainer() {
        this.emoji_container.classList.remove('show')
        this.search_el.value = ''
        this.emoji_div.innerHTML = ""
    }
}

function getUpdaterURL(page){
    let params = {}
    params['page'] = page
    switch(page){
        case 'profile':
            const profile_elem = document.querySelector("#profile")
            if(profile_elem){
                const pk = profile_elem.dataset.pk
                const updated_ts = profile_elem.dataset.updated_ts
                params['pk'] = pk
                params['updated_ts'] = updated_ts
            }
        case 'messages_from':
            const messages_elem = document.querySelector("#messages_from")
            if(messages_elem){
                const messages_pk = messages_elem.dataset.contact
                params['pk'] = messages_pk
                let nodes = document.querySelectorAll('.msg[data-dt]')
                params['dt'] = nodes[nodes.length-1].dataset.dt
            }
    }
    return '/upd?' + Object.keys(params).map(key => key + '=' + params[key]).join('&');
}

function handleUpdaterResponse(page, d){
    switch(page){
        case 'profile':
            if("profile" in d){
                profile = d.profile
                document.querySelector(".profile-about").innerText = profile.about
                document.querySelector("#profile").dataset.updated_ts = profile.updated_at
                const name_els = document.querySelectorAll(".profile-name");
                for (const name_el of name_els) {
                    name_el.innerText = profile.name
                }
                const pic_els = document.querySelectorAll(".profile-pic");
                for (const pic_el of pic_els) {
                    pic_el.setAttribute("src", profile.pic)
                }
            }
        case 'messages_from':
            if("messages" in d){
                messages = d.messages
                const messages_elem = document.querySelector("#messages_from")
                let shouldScroll = false
                if ((window.innerHeight + Math.ceil(window.pageYOffset)) >= document.body.offsetHeight) {
                   shouldScroll = true
                }
                messages_elem.innerHTML += messages
                if(shouldScroll){
                    window.scrollTo(0, document.body.scrollHeight);
                }
                else{
                    notify('new messages')
                }
            }
    }
}

function notify(text, link=false){
    n = document.querySelector(".notify")
    if(n !== null) n.remove()
    if(link){
        el = document.createElement("a")
        el.href = link
    }
    else{
        el = document.createElement("span")
    }
    el.innerText = text
    document.body.append(el)
    el.classList.add('notify')
    setTimeout(function(){
        el.remove()
    }, 3500);
}

function defaultImage(img){
    img.onerror = "";
    img.src = img.dataset.dflt;
    img.srcset = img.dataset.dflt;
}

function popup(htm){
    const existing = document.querySelector('.popup')
    const existing_ol = document.querySelector('.popup-overlay')
    if(existing){
        existing.remove()
    }
    if(existing_ol){
        existing_ol.remove()
    }
    overlay = document.createElement('div')
    overlay.classList.add('popup-overlay')
    the_popup = document.createElement('div')
    the_popup.classList.add('popup', 'rnd')
    the_popup.innerHTML = htm
    overlay.onclick = function(){
        overlay.remove();
        the_popup.remove();
        document.querySelector('.main').classList.remove('blur')
    }
    document.body.append(overlay)
    document.body.append(the_popup)
    document.querySelector('.main').classList.add('blur')
}

function fetchGet(url, cb, cb_data = {}, response_type='text'){
    fetch(url, {
        method: 'get'
    }).then(function(response) {
        if(response_type == 'text') return response.text();
        else if(response_type == 'json') return response.json();
    }).then(function(response) {
        cb(response, cb_data)
    }).catch(function(err) {
        console.log(err);
    });
}

function uploadToCloud(form_el, cb){
    const main_el = document.querySelector('.main')
    const settings = JSON.parse(main_el.dataset.settings)

    const files = form_el.querySelector("[type=file]").files;
    const cloudFormData = new FormData();
    for (let i = 0; i < files.length; i++) {
        let file = files[i];
        cloudFormData.append("file", file);
        cloudFormData.append("upload_preset", settings['cloudinary_upload_preset']);
        const cloud_url = 'https://api.cloudinary.com/v1_1/'+settings['cloudinary_cloud']+'/auto/upload'
        fetch(cloud_url, {
            method: "POST",
            body: cloudFormData
        }).then((response) => {
            return response.text();
        }).then((data) => {
            cb(data, form_el)
        });
    }
}

function fetchFromForm(url, form_el, cb, cb_data = {}, response_type='text'){
    const formData = new FormData(form_el);
    const data = [...formData.entries()];
    const options = {
        method: 'POST',
        body: JSON.stringify(data),
        headers: {
            'Content-Type': 'application/json'
        }
    }
    fetch(url, options).then(function(response) {
        if(response_type == 'text') return response.text();
        else if(response_type == 'json') return response.json();
    }).then(function(response) {
        cb(response, cb_data)
    }).catch(function(err) {
        console.log(err)
    });
}

function clipboard(str){
    navigator.clipboard.writeText(str);
    notify('copied')
}


function match_mentions(str){
    var pattern = /\B@[a-z0-9_-]+/gi;
    return str.match(pattern);
}

function setCloudUploads(form){

    if(form){
        const toolbar = form.querySelector('.toolbar')
        const label = document.createElement('label')
        toolbar.append(label)
        const input = document.createElement('input')
        input.setAttribute('type', 'file')
        input.setAttribute('name', 'img')
        input.setAttribute('multiple', true)
        label.append(input)
        const icon = document.createElement('img')
        icon.src = '/static/img.svg'
        icon.classList.add('icon-lg')
        label.append(icon)

        const hidden_input = document.createElement('input')
        hidden_input.setAttribute('type', 'hidden')
        hidden_input.setAttribute('name', 'uploads')
        form.append(hidden_input)
        input.style.display = 'none';
        input.addEventListener('change', (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadToCloud(form, function(data, elem){
                const d = JSON.parse(data)
                const im = document.createElement('img')
                im.src = d.secure_url
                elem.querySelector('.media_uploads').append(im)
                const uploads_input = elem.querySelector('[name="uploads"]')
                uploads_input.value += ' '+d.secure_url
            })
        });
    }
}

function lazyloadIntersectionObserver(lazyloadImages) {
	console.log("lazyloadIntersectionObserver")
	let imageObserver = new IntersectionObserver(function(entries, observer) {
		entries.forEach(function(entry) {
			if(entry.isIntersecting) {
				let image = entry.target;
				image.src = image.dataset.src;
				image.srcset = image.dataset.srcset;
				image.classList.remove("lazy-load");
				imageObserver.unobserve(image);
			}
		});
	});
	lazyloadImages.forEach(function(image) {
		imageObserver.observe(image);
	});
}

function lazyloadNoIntersectionObserve(lazyloadImages) {
	let lazyloadThrottleTimeout;

	function lazyload() {
		if(lazyloadThrottleTimeout) { clearTimeout(lazyloadThrottleTimeout); }
		lazyloadThrottleTimeout = setTimeout(function() {
			let scrollTop = window.pageYOffset;
			lazyloadImages.forEach(function(img) {
			if(img.offsetTop < (window.innerHeight + scrollTop)) {
				img.src = img.dataset.src;
				img.srcset = img.dataset.srcset;
				img.classList.remove('lazy-load');
			}
		});
		if(lazyloadImages.length == 0) {
			document.removeEventListener("scroll", lazyload);
			window.removeEventListener("resize", lazyload);
			window.removeEventListener("orientationChange", lazyload);
		}}, 20);
	}
	document.addEventListener("scroll", lazyload);
	window.addEventListener("resize", lazyload);
	window.addEventListener("orientationChange", lazyload);
}

function lazyLoad() {
	console.log("lazyLoad()")
	let lazyloadImages = document.querySelectorAll("img.lazy-load");
	if("IntersectionObserver" in window) {
		lazyloadIntersectionObserver(lazyloadImages);
	} else {
		lazyloadNoIntersectionObserve(lazyloadImages);
	}
}

window.addEventListener("load", function () {

    if (document.querySelector(".main[data-page='home']") != null){
        new bijaFeed();
        new bijaNotes();
        new bijaNotePoster();
    }
    if (document.querySelector(".main[data-page='note']") != null){
        new bijaNotes();
        new bijaThread();
    }
    if (document.querySelector(".main[data-page='topic']") != null){
        new bijaFeed();
        new bijaNotes();
        new bijaTopic();
    }

    if (document.querySelector(".main[data-page='profile']") != null){
        new bijaFeed();
        new bijaNotes();
        new bijaProfile();
    }
    if (document.querySelector(".main[data-page='profile-me']") != null){
        new bijaFeed();
        new bijaNotes();
        new bijaProfile();
    }
    if (document.querySelector(".main[data-page='following']") != null){
        new bijaProfile();
    }
    if (document.querySelector(".main[data-page='messages_from']") != null){
        new bijaMessages();
    }
    if (document.querySelector(".main[data-page='settings']") != null){
        new bijaSettings();
    }

    if (document.querySelector(".main[data-page='search']") != null){
        new bijaNotes();
    }

    SOCK();

    new bijaNoteTools();
    new bijaSearch();

    const btns = document.querySelectorAll('.clipboard');
    for (const btn of btns) {
        btn.addEventListener('click', (e) => {
            clipboard(btn.dataset.str);
        });
    }

    const main_el = document.querySelector('.main')
    if(main_el && main_el.dataset.settings){
        const settings = JSON.parse(main_el.dataset.settings)
        if(settings['cloudinary_cloud'] !== undefined){
            const upload_form = document.querySelector('#new_post_form')
            setCloudUploads(upload_form)
        }
    }

    const logout = document.querySelector('.logout')
    if(logout){
        logout.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            fetchGet('/logout', function(){
                document.querySelector('.main').innerHTML = "<h1>Shutting down...</h1>"
            }, {})
        });
    }

});

document.addEventListener("DOMContentLoaded", function() { lazyLoad(); });
