function SOCK() {

    var socket = io.connect();
    socket.on('connect', function() {
        socket.emit('new_connect', {data: true});
    });
    socket.on('message', function(data) {
        updateMessageThread(data);
    });
    socket.on('new_message', function(data) {
        notifyNewMessage(data);
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

let notifyNewMessage = function(){
    const a_el = document.querySelector('.archive_fetcher .n_fetched')
    if(a_el){
        const fetching_archive = a_el.dataset.active == '1'
        if(fetching_archive){
            const n = parseInt(a_el.innerText)+1
            a_el.innerText = n
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
    const a_el = document.querySelector('.archive_fetcher .n_fetched')
    if(a_el){
        const fetching_archive = a_el.dataset.active == '1'
        if(fetching_archive){
            const n = parseInt(a_el.innerText)+1
            a_el.innerText = n
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
//        if(profile.nip05 != null && profile.nip05.length > 0 && profile.nip05_validated){
//            const nip5 = name_el.querySelector('.nip5')
//            if(nip5){
//                nip5.innerText = profile.nip05
//            }
//        }
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
        this.input_el = document.querySelector('input[name="search_term"]');
        this.hint_el = document.querySelector('#search_hints')
        this.tips_el = document.querySelector('#search_tips')
        this.setEventListeners()
    }

    setEventListeners(){
        this.input_el.addEventListener("keyup", (event)=>{
            this.hint_el.innerHTML = ''
            const val = this.input_el.value
            if(val.length > 0){
                this.tips_el.style.display = 'none'
            }
            else{
                this.tips_el.style.display = 'block'
            }
            if (val.substring(0, 1) == '@' && val.length > 1){
                this.searchByName(val.substring(1))
            }
        })
        this.setSearchTips()
        this.input_el.addEventListener("focus", (event)=>{
            if(this.input_el.value.length == 0){
                this.tips_el.style.display = 'block'
            }
        })
        this.input_el.addEventListener("blur", (event)=>{
            this.tips_el.style.display = 'none'
        })
    }

    searchByName(name){
        const cb = function(response, data){
            if(response['result']){
                data.context.showNameHints(response['result'], data.search, data.context)
            }
        }
        fetchGet('/search_name?name='+name, cb, {
            'context':this,
            'search':name
        }, 'json')
    }

    showNameHints(results, search_str, context){
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
                    context.input_el.value = context.input_el.value.replace('@'+search_str, '@'+name['name'])
                    context.input_el.parentElement.submit();
                });
                ul.append(li)
            }
            context.hint_el.append(ul)
        }
    }
    
    setSearchTips() {
        const tips_elems = this.tips_el.querySelectorAll('li')
        tips_elems.forEach(elem => {
            elem.addEventListener('mousedown', (event) => {
                event.preventDefault()
            }); 
            elem.addEventListener("click", (event) => {
                let fill_content = elem.getAttribute('data-fill')
                console.log(fill_content)
                if (fill_content.length > 0) {
                    this.input_el.value = fill_content
                } else {
                    this.input_el.value = ''
                }
                this.input_el.blur()
                this.input_el.focus()
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

        this.auto_filler = document.querySelector('#name-hints');
        this.setNameAutoFiller()
        document.addEventListener("profileReq", (event)=>{
            this.anchorNameAutoFiller(event.detail.elem)
        })
    }

    setEventListeners(){
        const els = document.querySelectorAll('textarea.note-textarea');
        for(const el of els){
            if(!el.dataset.toolset){
                el.dataset.toolset = true
                this.setNameHintFetch(el)
                this.setRegisterCursorPos(el)
            }
        }
    }

    setRegisterCursorPos(el){
        el.addEventListener("keyup", (event)=>{
            el.dataset.pos = event.target.selectionStart
        });
        el.addEventListener("click", (event)=>{
            el.dataset.pos = event.target.selectionStart
        });
        el.addEventListener("focus", (event)=>{
            el.dataset.pos = event.target.selectionStart
        });
    }

    anchorNameAutoFiller(elem){

        const pos = elem.getBoundingClientRect()
        this.auto_filler.style.top = parseInt(pos.bottom)+'px'
        this.auto_filler.style.left = parseInt(pos.left)+'px'
    }

    setNameAutoFiller(){

    }

    setNameHintFetch(reply_el){
        reply_el.addEventListener("keyup", (event)=>{
            this.auto_filler.innerHTML = ''
            const matches = match_mentions(reply_el.value);
            if(matches){
                document.dispatchEvent(new CustomEvent("profileReq", {
                    detail: {elem: reply_el}
                }));
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
                            data.context.showNameHints(data.hint_elem, data.reply_elem, response['result'], data.search)
                        }
                    }
                    fetchGet('/search_name?name='+name, cb, {
                        'context':this,
                        'hint_elem':this.auto_filler,
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


        const container = document.querySelector('#note-poster');
        const ct = document.querySelector('#new_post');
        const max_btn = form.querySelector('.maximise');
        if(ct){
            ct.addEventListener('focus', (e) => {
                ct.classList.add('focus')
            });
        }
        max_btn.addEventListener('click', (e) => {
            if(container.classList.contains('expanded')){
                container.classList.remove('expanded')
                ct.focus()
                max_btn.style.display = 'block'
            }
            else{
                container.classList.add('expanded')
                ct.focus()
                max_btn.style.display = 'block'
            }
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

        this.setRelaySettingClickedEvents()

        this.setDeleteKeysClicked()

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
        this.setThemeSliders()
    }

    setThemeSliders(){
        const sliders = document.querySelectorAll('.slider')
        for(const slider of sliders){
            const rel = slider.dataset.v
            slider.addEventListener("input", (event)=>{
                console.log('--'+slider.dataset.v)
                document.querySelector('.demo[data-rel="'+rel+'"]').style.setProperty('--'+rel, slider.value+'px');
            });
            slider.addEventListener("mousedown", (event)=>{
                const d_els = document.querySelectorAll('.demo')
                for(const d_el of d_els){
                    d_el.style.display = 'none'
                }
                document.querySelector('.demo[data-rel="'+rel+'"]').style.display = 'block'
            });
            slider.addEventListener("mouseup", (event)=>{
                const d_els = document.querySelectorAll('.demo')
                for(const d_el of d_els){
                    d_el.style.display = 'none'
                }
            });

        }
        const btn = document.querySelector(".update_styles");
        btn.addEventListener("click", (event)=>{
            event.preventDefault();
            event.stopPropagation();
            const style_form = document.querySelector("#style_form")

            const cb = function(response, data){
                location.reload();
            }
            fetchFromForm('/update_settings', style_form, cb, {}, 'json')
        });
        const dflt_btn = document.querySelector(".default_styles");
        dflt_btn.addEventListener("click", (event)=>{
            event.preventDefault();
            event.stopPropagation();

            const scb = function(response, data){
                location.reload();
            }
            fetchGet('/default_styles', scb, {}, 'json')
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

    setRelaySettingClickedEvents(){
        const relays = document.querySelectorAll(".relay[data-url]");
        for (const relay of relays) {
            this.setRelaySettingClickedEvent(relay)
        }
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
    }

    setRelaySettingClickedEvent(elem){

        elem.querySelector(".del-relay").addEventListener("click", (event)=>{
            const cb = function(response, data){
                data.context.reloadRelayList()
            }
            fetchGet('/del_relay?url='+encodeURIComponent(elem.dataset.url), cb, {'context': this})
        });
        elem.querySelectorAll(".relay_setting").forEach(function(s){
            s.addEventListener("click", (event)=>{
                const cb = function(response, data){
                console.log(response.success)
                    if(response.success == true){
                        notify('updated')
                    }
                    else{
                        notify('not updated')
                    }
                }
                const url = encodeURIComponent(elem.dataset.url)
                const setting = encodeURIComponent(event.srcElement.dataset.setting)
                fetchGet('/update_relay?url='+url+'&'+setting+'='+event.srcElement.checked, cb, {'context': this}, 'json')
            });
        })
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
            data.context.setRelaySettingClickedEvents()
        }
        fetchGet('/reload_relay_list', cb, {'context': this})
    }
}

class bijaThread{

    constructor(){
        document.addEventListener("newNote", (event)=>{
            console.log("newNote")
            const el = document.querySelector(".note-container[data-id='"+event.detail.id+"']")
            console.log(el)
            if( (el && el.classList.contains('placeholder')) || !el){
                fetchGet('/thread_item?id='+event.detail.id, this.processNewNoteInThread, {'elem': el, 'context':this})
            }
        });
        const items = document.querySelectorAll(".note-container")
        if (items.length > 1){
            items[0].classList.add('ancestor')
        }
        const reply_items = document.querySelectorAll(".note-container.reply")
        const main_item = document.querySelector(".note-container.main")
        if (reply_items.length > 0 && main_item){
            main_item.classList.add('ancestor')
        }
        const load_link = document.querySelector(".load_more")
        if(load_link){
            this.setLoadMore(load_link)
        }
    }

    setLoadMore(load_link){

        load_link.addEventListener('click', (e) => {
            event.preventDefault();
            event.stopPropagation();
            const cb = function(response, data){
                if(response.length > 0){
                    const doc = new DOMParser().parseFromString(response, "text/html")
                    const new_elem = doc.body.firstChild
                    new_elem.classList.add('ancestor')
                    load_link.parentNode.insertAdjacentElement('afterend', new_elem);
                    const root = document.querySelector(".note-container.root")
                    if(new_elem.dataset.parent){
                        if(root && new_elem.dataset.parent.length < 1 && new_elem.dataset.root == root.dataset.id){
                            load_link.parentNode.remove()
                        }
                        else{
                            load_link.dataset.rel = new_elem.dataset.parent
                        }
                    }
                    else{
                        load_link.parentNode.remove()
                    }
                    document.dispatchEvent(new Event('newContentLoaded'))
                }
            }
            fetchGet('/thread_item?id='+encodeURIComponent(load_link.dataset.rel), cb, {})
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
            data.elem.replaceWith(new_item)
            document.dispatchEvent(new Event('newContentLoaded'))
        }
    }
}

class bijaMessages{
    constructor(){
        const main_el = document.querySelector('.main')
        let page = main_el.dataset.page
        if(page == 'messages_from'){
            window.scrollTo(0, document.body.scrollHeight);
            this.setSubmitMessage()
            this.setCfgLoader()
        }
        const mark_read_btn = document.querySelector('#mark_all_read');
        if(mark_read_btn){
            this.setAllReadBtn(mark_read_btn)
        }
        const empty_junk_btn = document.querySelector('#empty_junk');
        if(empty_junk_btn){
            this.setEmptyJunkBtn(empty_junk_btn)
        }
        const archive_fetcher = document.querySelector('#fetch_archived');
        if(archive_fetcher){
            this.setArchiveFetcher(archive_fetcher)
        }
    }

    setAllReadBtn(btn){
        const cb = function(response, data){
            location.reload()
        }
        btn.addEventListener("click", (event)=>{
            event.preventDefault();
            fetchGet('/mark_read', cb, {})
        });
    }

    setEmptyJunkBtn(btn){
        const cb = function(response, data){
            location.reload()
        }
        btn.addEventListener("click", (event)=>{
            event.preventDefault();
            fetchGet('/empty_junk', cb, {})
        });
    }

    setCfgLoader(){
        const cfg_loaders = document.querySelectorAll('.cfg_loader')
        for(const el of cfg_loaders){
            const cb = function(response, data){
                location.reload()
            }
            el.addEventListener("click", (event)=>{
                event.preventDefault();
                fetchFromForm('/load_cfg', el, cb, {})
            });
        }
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

    setArchiveFetcher(el){
        el.addEventListener('change', (e) => {
            const container =  document.querySelector('.archive_fetcher')
            const a_el = container.querySelector('.n_fetched')
            container.querySelector('.loading').style.display = 'flex'
            a_el.dataset.active = "1"
            a_el.innerText = '0'
            const cb = function(response, data){

            }
            fetchGet('/fetch_archived_msgs?tf='+el.value, cb, {})
        });
    }
}

class bijaProfile{

    constructor(){

        const profile_el = document.querySelector('#profile')
        this.public_key = profile_el.dataset.pk

        this.setEventListeners()
        const main_el = document.querySelector('.main')
        let page = main_el.dataset.page
        if(['profile', 'profile-me'].includes(page)){
            page = 'posts'
        }
        const nav_el = main_el.querySelector('.profile-menu a[data-page="'+page+'"]')
        if(nav_el){
            nav_el.classList.add('actv')
        }
        const unblock = main_el.querySelector('.unblock_form')
        if(unblock){
            this.setUnblockForm(unblock)
        }

    }

    setEventListeners(){

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
                else{
                    document.querySelector(".profile-img-up").disabled = true;
                }
            }
        }
        const invalid_nip5 = document.querySelector('#profile .warn')
        if(invalid_nip5){
            this.setNip5Validator()
        }
        const share_btn = document.querySelector('.share-profile')
        if(share_btn){
            this.setShareBtn(share_btn)
        }
        const ln_btn = document.querySelector('.lightning')
        if(ln_btn){
            this.setLNBtn(ln_btn)
        }
        const archive_fetcher = document.querySelector('#fetch_archived');
        if(archive_fetcher){
            this.setArchiveFetcher(archive_fetcher)
        }
    }

    setUnblockForm(form){
        const btn = form.querySelector("button")
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const cb = function(response, data){
                //location.reload()
            }
            fetchFromForm('/unblock', form, cb, {}, 'json')
        });
    }

    setArchiveFetcher(el){
        el.addEventListener('change', (e) => {
            const container =  document.querySelector('.archive_fetcher')
            const a_el = container.querySelector('.n_fetched')
            container.querySelector('.loading').style.display = 'flex'
            a_el.dataset.active = "1"
            a_el.innerText = '0'
            let nodes = document.querySelectorAll('.ts[data-ts]')
            let ts = Math.floor(Date.now() / 1000)
            if(nodes.length > 0){
                ts = nodes[nodes.length-1].dataset.ts
            }
            const cb = function(response, data){

            }
            fetchGet('/fetch_archived?pk='+this.public_key+'&tf='+el.value+'&ts='+ts, cb, {})
        });
    }

    setLNBtn(el){
        el.addEventListener('click', (e) => {
            const cb = function(response, data){
                popup(response)
            }
            fetchGet('/get_ln_details?pk='+this.public_key, cb, {})
        });
    }
    setShareBtn(el){
        el.addEventListener('click', (e) => {
            const cb = function(response, data){
                popup(response)
            }
            fetchGet('/get_profile_sharer?pk='+this.public_key, cb, {})
        });
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
}

class bijaNotes{
    constructor(){
        this.setEventListeners()
        document.addEventListener('newContentLoaded', ()=>{
            this.setEventListeners()
            lazyLoad()
        });
        setInterval(this.tsUpdater, 120000);
    }

    tsUpdater(){
        const notes = document.querySelectorAll(".dt[data-ts]");
        const timestamps = []
        for (const n of notes) {
            timestamps.push(n.dataset.ts)
        }
        const cb = function(response, data){
            const stamps = JSON.parse(response)
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

            const boost_el = note.querySelector(".boost-link");
            if(boost_el){
                this.setBoostClickedEvents(boost_el)
            }

            const like_el = note.querySelector("a.like");
            if(like_el){
                this.setLikeClickedEvents(like_el)
            }

            const im_el = note.querySelector(".image-attachment img");
            if(im_el){
                this.setImageClickEvents(note.querySelector(".image-attachment"))
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
                emoji_link.addEventListener('click', (e) => {
                    document.dispatchEvent(new CustomEvent("emojiReq", {
                        detail: {elem: note}
                    }));
                });
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

    setImageClickEvents(container){
        const elems = container.querySelectorAll('img')
        for (const elem of elems) {
            elem.addEventListener("click", (event)=>{
                const im = document.createElement('img')
                im.setAttribute('referrerpolicy', 'no-referrer')
                im.src = elem.dataset.src
                popup('')
                document.querySelector('.popup').append(im)
            });
        }
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
                    lazyLoad()
                    document.querySelector('.popup .emojis').addEventListener('click', (e) => {
                        document.dispatchEvent(new CustomEvent("emojiReq", {
                            detail: {elem: document.querySelector('.popup')}
                        }));
                    });
                }
            }
            fetchGet('/quote_form?id='+note_id, cb, {'context': this})
        })
    }
    setBoostClickedEvents(elem){
        elem.addEventListener('click', (e) => {
            event.preventDefault();
            event.stopPropagation();
            const note_id = elem.dataset.rel
            const cb = function(response, data){
                if(response['status'] == true){
                    notify('boosted')
                }
                else{
                    notify('already boosted')
                }
            }
            fetchGet('/boost?id='+note_id, cb, {}, 'json')
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
                            popup("<pre class='break-word'><h3>Raw event data</h3>"+JSON.stringify(JSON.parse(response['data']), null, 2)+"</pre>")
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
            else if(tool == 'share'){
                tool_el.addEventListener('click', (e) => {
                    event.preventDefault();
                    event.stopPropagation();
                    const get_share_cb = function(response, data){
                        if(response){
                            popup(response)
                        }
                    }
                    fetchGet('/get_share?id='+note_id, get_share_cb, {context:this})
                })
            }
            else if(tool == 'block'){
                tool_el.addEventListener('click', (e) => {
                    event.preventDefault();
                    event.stopPropagation();
                    const get_block_cb = function(response, data){
                        if(response){
                            popup(response)
                            lazyLoad()
                            data.context.setBlockForm()
                        }
                    }
                    fetchGet('/confirm_block?note='+note_id, get_block_cb, {context:this})
                })
            }
        }
    }

    setLikeCountClickEvents(elem, id){
        elem.addEventListener('click', (e) => {
            const cb = function(response, data){
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

    setBlockForm(){
        const form = document.querySelector("#block_form")
        const btn = form.querySelector("input[type='submit']")
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const cb = function(response, data){
                if(response['event_id']){
                   location.reload()
                }
            }
            fetchFromForm('/block', form, cb, {}, 'json')
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
        if(['home', 'profile-me'].includes(main_el.dataset.page)){
            main_el.querySelector('#note-poster .emojis').addEventListener('click', (e) => {
                document.dispatchEvent(new CustomEvent("emojiReq", {
                    detail: {elem: main_el.querySelector('#note-poster')}
                }));
            });
        }

        this.page = main_el.dataset.page
        this.data = {};
        this.loading = 0;
        this.listener = () => this.loader(this);
        window.addEventListener('scroll', this.listener);
        this.pageLoadedEvent = new Event("newContentLoaded");
        this.requestNextPage(Math.floor(Date.now() / 1000))
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
            fetchGet('/topic_feed?before='+ts+'&topic='+encodeURIComponent(topic_elem.dataset.topic), cb, {'context': this})
        }
        else if(this.page == 'search'){
            const search_elem = document.querySelector("#search_results")
            fetchGet('/search_feed?before='+ts+'&search='+encodeURIComponent(search_elem.dataset.search), cb, {'context': this})
        }
    }

    loadArticles(response){
        const doc = new DOMParser().parseFromString(response, "text/html")
        const htm = doc.body.firstChild
        document.getElementById("feed").append(htm);
        const o = this
        setTimeout(function(){
            o.loading = 0;
        }, 200)
    }
}

class bijaProfileBriefs{
    constructor(){
        document.addEventListener('newContentLoaded', ()=>{
            this.setEventListeners()
        });
        this.setEventListeners()
    }
    setEventListeners(){
        const btns = document.querySelectorAll(".follow-btn");
        for (const btn of btns) {
            btn.classList.remove('follow-btn')
            btn.addEventListener("click", (event)=>{
                event.preventDefault();
                event.stopPropagation();
                let id = btn.dataset.rel;
                let state = btn.dataset.state;
                let upd = btn.dataset.upd;
                this.setFollowState(btn, state, upd);
                return false;
            });
        }
        const block_btns = document.querySelectorAll(".block-btn");
        for (const btn of block_btns) {
            btn.addEventListener('click', (e) => {
                event.preventDefault();
                event.stopPropagation();
                const get_block_cb = function(response, data){
                    if(response){
                        popup(response)
                        lazyLoad()
                        data.context.setBlockForm()
                    }
                }
                fetchGet('/confirm_block?pk='+btn.dataset.rel, get_block_cb, {context:this})
            })
        }
    }

    setBlockForm(){
        const form = document.querySelector("#block_form")
        const btn = form.querySelector("input[type='submit']")
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const cb = function(response, data){
                if(response['event_id']){
                   location.reload()
                }
            }
            fetchFromForm('/block', form, cb, {}, 'json')
        });
    }

    setFollowState(btn, state, upd){
        const cb = function(response, data){
            if(data.upd == '1'){
                document.querySelector(".profile-tools").innerHTML = response
            }
            else{
                if(data.state == 1){
                    data.btn.innerText = 'unfollow'
                    data.btn.dataset.state = 0
                }
                else{
                    data.btn.innerText = 'follow'
                    data.btn.dataset.state = 1
                }
            }
        }
        fetchGet('/follow?id='+btn.dataset.rel+"&state="+state+"&upd="+upd, cb, {'upd':upd,'btn':btn,'state':state})
    }
}

class bijaFollowers{
    constructor(){
        const main_el = document.querySelector(".main[data-page]")
        this.page = main_el.dataset.page
        this.list_el = document.querySelector(".following-list")
        this.page_n = parseInt(this.list_el.dataset.page)
        const profile_el = document.querySelector("#profile")
        this.pk = profile_el.dataset.pk
        this.data = {};
        this.loading = 0;
        this.listener = () => this.loader(this);
        window.addEventListener('scroll', this.listener);
        this.pageLoadedEvent = new Event("newContentLoaded");
        this.requestNextPage(Math.floor(Date.now() / 1000))
    }

    loader(o){
        if ((window.innerHeight + window.innerHeight + window.scrollY) >= document.body.offsetHeight && o.loading == 0){
            o.requestNextPage();
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
                data.context.page_n += 1
                data.context.loadArticles(response, data.context);
                document.dispatchEvent(data.context.pageLoadedEvent);
            }
            lazyLoad()
        }
        fetchGet('/followers_list_next?n='+this.page_n+'&list='+encodeURIComponent(this.page)+'&pk='+encodeURIComponent(this.pk), cb, {'context': this})
    }

    loadArticles(response, context){
        const doc = new DOMParser().parseFromString(response, "text/html")
        const htm = doc.body.firstChild
        context.list_el.append(htm);
        const o = this
        setTimeout(function(){
            o.loading = 0;
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
    target_el = null
    active = false
    constructor(target_el){
        this.emoji_container = document.querySelector('#emoji_selector')
        this.search_el = this.emoji_container.querySelector('#emoji_selector input')
        this.emoji_div = this.emoji_container.querySelector('#emoji_selector div')

        this.setEventsListeners()
    }
    anchor(elem){
        this.reset()
        this.target_el = elem
        this.trigger_btn = this.target_el.querySelector('.emojis')
        this.emoji_container.classList.add('show')
        const pos = this.trigger_btn.getBoundingClientRect()
        this.emoji_container.style.top = parseInt(pos.top)+'px'
        this.emoji_container.style.left = parseInt(pos.left - this.emoji_container.offsetWidth)+'px'
        this.fetch()
        this.active = true

        window.addEventListener("click", this.closeOnClickOutside);
    }
    fetch(){
        fetchGet('/emojis?s='+this.search_el.value, this.loadEmojis, {'context': this}, 'json')
    }
    reset(){
        this.search_el.value = ''
        this.emoji_div.innerHTML = ""
    }
    setEventsListeners(){
        document.addEventListener("emojiReq", (event)=>{
            this.anchor(event.detail.elem)
        })
        this.search_el.addEventListener("keyup", (event)=>{
            this.fetch()
        });
        document.body.addEventListener("mouseup", (event)=>{
            if (this.active && !this.emoji_container.contains(event.target)) {
                this.close()
            }
        });
    }
    loadEmojis(response, data){
        if(response){
            data.context.emoji_div.innerHTML = ""
            data.context.search_el.focus()
            document.addEventListener("scroll", data.context.close);
            for(const item of response.emojis){
                const a = document.createElement('a')
                a.href = '#'
                a.innerText = item
                a.addEventListener("click", (event)=>{
                    event.stopPropagation();
                    event.preventDefault();
                    // data.context.target_el.querySelector('textarea').value += a.innerText
                    data.context.insert(data.context.target_el.querySelector('textarea'), a.innerText)
                    data.context.updateRecent(a.innerText)
                    data.context.reset()
                    data.context.close()
                });
                data.context.emoji_div.append(a)
            }
        }
    }
    insert(el, val){
        const pos = parseInt(el.dataset.pos)
        el.value = el.value.substring(0, pos) + val + el.value.substring(pos, el.value.length);
        el.setSelectionRange(pos+1, pos+1)
        el.focus()
    }
    updateRecent(emoji){
        fetchGet('/recent_emojis?s='+emoji, false, {})
    }
    close() {
        document.removeEventListener("scroll", this.close);
        const container = document.querySelector('#emoji_selector')
        container.classList.remove('show')
        container.querySelector('input').value = ''
        container.querySelector('div').innerHTML = ""
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
        if(cb){
            cb(response, cb_data)
        }
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
	let imageObserver = new IntersectionObserver(function(entries, observer) {
		entries.forEach(function(entry) {
			if(entry.isIntersecting) {
				let image = entry.target;
				image.src = image.dataset.src;
				image.classList.remove("lazy-load");
				imageObserver.unobserve(image);
			    setTimeout(function(){
			        if(!image.complete){
			            if(image.dataset.dflt){
			                image.src = image.dataset.dflt
			            }
			            else{
			                image.src = '/static/blank.png'
			            }
			        }
			    }, 3000)
			}
		});
	});
	lazyloadImages.forEach(function(image) {
		imageObserver.observe(image);
	});
}
function ogObserver(elems){
    let ogObserve = new IntersectionObserver(function(entries, observer) {
		entries.forEach(function(entry) {
			if(entry.isIntersecting) {
				let el = entry.target;
				el.classList.remove("og-container");
				fetchOG(el, el.dataset.rel)
				ogObserve.unobserve(el);
			}
		});
	});
    elems.forEach(function(elem) {
		ogObserve.observe(elem);
	});
}
function fetchOG(elem, url){
    const cb = function(response, data){
        const doc = new DOMParser().parseFromString(response, "text/html")
        const htm = doc.body.firstChild
        elem.replaceWith(htm)
    }
    fetchGet('/fetch_ogs?url='+encodeURIComponent(url), cb, {})
}

function noteObserver(elems){
    let noteObserve = new IntersectionObserver(function(entries, observer) {
		entries.forEach(function(entry) {
			if(entry.isIntersecting) {
				let el = entry.target;
				fetchNote(el, el.dataset.id)
				noteObserve.unobserve(el);
			}
		});
	});
    elems.forEach(function(elem) {
		noteObserve.observe(elem);
	});
}
function fetchNote(elem, id){
    const cb = function(response, data){
        if(response.length > 0){
            const doc = new DOMParser().parseFromString(response, "text/html")
            const htm = doc.body.firstChild
            if(!htm.classList.contains('placeholder')){
                elem.replaceWith(htm)
                lazyLoad()
            }
        }
    }
    fetchGet('/thread_item?id='+encodeURIComponent(id), cb, {})
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
	let lazyloadImages = document.querySelectorAll("img.lazy-load");
	let lazyLoadOGs = document.querySelectorAll(".og-container");
	let lazyLoadNotes= document.querySelectorAll(".note-container.placeholder");
	if("IntersectionObserver" in window) {
		lazyloadIntersectionObserver(lazyloadImages);
		ogObserver(lazyLoadOGs)
		noteObserver(lazyLoadNotes)
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
        new bijaNotePoster();
    }
    if (document.querySelector(".main[data-page='following']") != null){
        new bijaProfile();
        new bijaFollowers();
    }
    if (document.querySelector(".main[data-page='followers']") != null){
        new bijaProfile();
        new bijaFollowers();
    }
    if (document.querySelector(".main[data-page='messages_from']") != null){
        new bijaMessages();
    }
    if (document.querySelector(".main[data-page='messages']") != null){
        new bijaMessages();
    }
    if (document.querySelector(".main[data-page='settings']") != null){
        new bijaSettings();
    }

    if (document.querySelector(".main[data-page='search']") != null){
        new bijaFeed();
        new bijaNotes();
    }

    if (document.querySelector(".main[data-page='boosts']") != null){
        new bijaNotes();
    }
    new Emojis();
    new bijaProfileBriefs();

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
    lazyLoad();
});