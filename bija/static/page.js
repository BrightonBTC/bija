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

    socket.on('new_reaction', function(note_id) {
        updateInteractionCount(note_id, '.likes');
    });
    socket.on('new_reply', function(note_id) {
        updateInteractionCount(note_id, '.reply-n');
    });
    socket.on('new_reshare', function(note_id) {
        updateInteractionCount(note_id, '.quote-n');
    });
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
        if(profile.name.length > 0){
            const nm = name_el.querySelector('.name')
            if(nm){
                nm.innerText = profile.name
            }
        }
        if(profile.nip05 !== null && profile.nip05.length > 0 && profile.nip05_validated){
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
                    window.location.href = '/note?id='+response['root']+'#'+response['event_id']
//                   notify('Note created. View now?', '/note?id='+response['root']+'#'+response['event_id'])
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

        const relays = document.querySelectorAll(".relay[data-url]");
        for (const relay of relays) {
            this.setRelayRemoveClickedEvent(relay)
        }

        this.setDeleteKeysClicked()

        const relay_btn = document.querySelector("#addrelay");
        relay_btn.addEventListener("click", (event)=>{
            event.preventDefault();
            event.stopPropagation();
            const form = document.querySelector("#relay_adder")

            const cb = function(response, data){
                if(response['success']){
                   notify('relay added')
                }
            }
            fetchFromForm('/add_relay', form, cb, {}, 'json')
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
            }
        });
    }

    setRelayRemoveClickedEvent(elem){
        elem.querySelector(".del-relay").addEventListener("click", (event)=>{
            const cb = function(response, data){
                data.elem.remove()
            }
            fetchGet('/del_relay?url='+elem.dataset.url, cb, {'elem': elem})
        });
    }

    setUpdateConnsClickedEvent(){
        const elem = document.querySelector(".refresh_connections");
        elem.addEventListener("click", (event)=>{
            const cb = function(response, data){
                // TODO: update page
            }
            fetchGet('/refresh_connections', cb, {})
        });
    }
}

class bijaThread{

    constructor(){
        this.root = false;
        this.focussed = false;
        this.replies = [];
        this.setFolding();
        window.addEventListener("hashchange", (event)=>{
            this.setFolding();
        });
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
            console.log('new elem')
            if(new_item.dataset.parent.length > 0){
                const siblings = document.querySelectorAll(".note-container[data-parent='"+new_item.dataset.parent+"']")
                if(siblings.length > 0){
                    const last = Array.from(siblings).pop();
                    last.insertAdjacentElement("afterend", new_item);
                }
                else{
                    const parent = document.querySelector(".note-container[data-id='"+new_item.dataset.parent+"']")
                    if(parent){
                        parent.insertAdjacentElement("afterend", new_item);
                    }
                }
            }
            document.dispatchEvent(new Event('newContentLoaded'))
        }
        else{
            console.log('replace elem')
            data.elem.replaceWith(new_item)
            document.dispatchEvent(new Event('newContentLoaded'))
        }
        data.context.setFolding()
    }

    setFolding(){
        this.focussed = window.location.hash.substring(1);
        const container_el = document.querySelector('#thread-items')
        this.root = container_el.dataset.root
        const note_elems = document.querySelectorAll(".note-container")
        for (const n of note_elems) {
            n.classList.remove('main', 'ancestor', 'reply')
            n.style.display = 'none'
        }
        this.showRoot()
        this.showReplies()
        this.showMain()
    }

    showMain(){
        const main = document.querySelector(".note-container[data-id='"+this.focussed+"']")
        if(main){
            main.classList.add('main')
            main.style.display = 'flex'
            this.setReplyCount(main)
            if(main.dataset.parent.length > 0){
                this.showParent(main.dataset.parent, main)
            }
            if(this.replies.length > 0){
                main.classList.add('ancestor')
            }
            main.scrollIntoView({
                behavior: 'auto',
                block: 'center',
                inline: 'center'
            });
        }
        else{
            const elem = this.buildPlaceholder(this.focussed, this.focussed)
            document.querySelector('#thread-items').prepend(elem)
        }
    }

    showReplies(){
        this.replies = document.querySelectorAll(".note-container[data-parent='"+this.focussed+"']")
        for (const n of this.replies) {
            n.classList.add('reply')
            n.style.display = 'flex'
            this.setReplyCount(n)
        }
    }
    showRoot(){
        this.root_el = document.querySelector(".note-container[data-id='"+this.root+"']")
        if (this.root_el) {
            this.root_el.classList.add('root')
            this.root_el.style.display = 'flex'
        }
    }

    showParent(id, child){
        const el = document.querySelector(".note-container[data-id='"+id+"']");
        if(el){
            el.classList.add('ancestor');;
            el.style.display = 'flex';
            this.setReplyCount(el);
            const parent = el.dataset.parent;;
            if(parent && parent.length > 0){
                this.showParent(parent, el);
            }
        }
        else{
            const rel = child.dataset.rel
            const elem = this.buildPlaceholder(id, rel)
            if(child.dataset.rel == id){
                document.querySelector('#thread-items').prepend(elem)
            }
            else{
                child.parentElement.insertBefore(elem, child)
            }
        }
    }

    buildPlaceholder(id, rel){
        const new_container_el = document.createElement('div');
        new_container_el.dataset.id = id
        new_container_el.dataset.rel = rel
        new_container_el.dataset.parent = ''
        new_container_el.classList.add('note-container', 'placeholder')
        const new_el = document.createElement('div');
        new_el.innerHTML = "<p>Event ("+id+") not yet found on network</p>";
        new_el.classList.add('note-content')
        new_container_el.append(new_el)
        new_container_el.addEventListener("click", (event)=>{
            window.location.href = '/note?id='+rel+'#'+id
        });
        return new_container_el
    }

    setReplyCount(el){
        const id = el.dataset.id;
        const n = document.querySelectorAll(".note-container[data-parent='"+id+"']").length;
        const r_el = el.querySelector('.reply-n')
        if(r_el){
            if(n>0) r_el.innerText = n
            else r_el.innerText = ''
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
                this.setFollowState(id, state);
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
        }
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

    setFollowState(id, state){
        const cb = function(response, data){
            document.querySelector(".profile-tools").innerHTML = response
        }
        fetchGet('/follow?id='+id+"&state="+state, cb)
    }

}

class bijaNotes{
    constructor(){
        this.setEventListeners()
        document.addEventListener('newContentLoaded', ()=>{
            this.setEventListeners()
        });
    }

    setEventListeners(){
        const notes = document.querySelectorAll(".note[data-processed='0']");
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

            const content_el = note.querySelector(".note-content pre");
            this.setExpandableHeight(content_el)

            const im_el = note.querySelector(".image-attachment img");
            if(im_el){
                this.setImageClickEvents(im_el)
            }

            const like_n_el = note.querySelector(".likes.counts");
            if(like_n_el){
                this.setLikeCountClickEvents(like_n_el, note.dataset.id)
            }

        }
    }

    setImageClickEvents(elem){
        elem.addEventListener("click", (event)=>{
            const im = elem.parentElement.innerHTML
            popup(im)
        });
    }

    setExpandableHeight(elem){
        if(elem.offsetHeight > 150){
            elem.style.height = '150px'
            elem.style.overflow = 'hidden'
            elem.style.paddingBottom = '60px'
            elem.dataset.state = 0
            const reveal_btn = document.createElement('div')
            reveal_btn.classList.add('reveal')
            reveal_btn.innerHTML = '<span>show more</span>'
            elem.append(reveal_btn)
            reveal_btn.addEventListener("click", (event)=>{
                event.stopPropagation();
                const btn = elem.querySelector('span')
                if(elem.dataset.state == 0){
                    elem.style.height = 'auto'
                    elem.dataset.state = 1
                    btn.innerText = 'show less'
                }
                else{
                    elem.style.height = '150px'
                    elem.dataset.state = 0
                    btn.innerText = 'show more'
                }
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
                elem.querySelector('img').setAttribute('src', '/static/like.svg')
            }
            else{
                d.liked = 'True'
                elem.querySelector('img').setAttribute('src', '/static/liked.svg')
            }
            const cb = function(response, data){
                if(response['event_id']){
                    data.elem.dataset.disabled = false
                }
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
                window.location.href = '/note?id='+rel+'#'+id
            }
        });
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
        for (var i = 0; i < response.length; i++){
            let li = document.createElement('li')
            if(response[i].content == null || response[i].content.length < 1 || response[i].content == "+"){
                response[i].content = "🤍"
            }
            if(response[i].name == null || response[i].name.length < 1){
                response[i].name = response[i].public_key.substring(0, 21)+"..."
            }

            li.innerHTML = '<span>'+response[i].content+'</span><span>'+response[i].name+'</span>';
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
                window.location.href = '/note?u='+Date.now()+'&id='+response['root']+'#'+response['event_id']
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
            o.requestNextPage(nodes[nodes.length-1].dataset.ts);
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
        else{
            const profile_elem = document.querySelector("#profile")
            fetchGet('/profile_feed?before='+ts+'&pk='+profile_elem.dataset.pk, cb, {'context': this})
        }
    }

    loadArticles(response){
        const doc = new DOMParser().parseFromString(response, "text/html")
        const htm = doc.body.firstChild
        document.getElementById("main-content").append(htm);
        const o = this
        setTimeout(function(){
            o.loading = 0;
        }, 200)

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
}

function popup(htm){
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
    SOCK();

    new bijaNoteTools();
    new bijaSearch();

    const btns = document.querySelectorAll('.clipboard');
    for (const btn of btns) {
        btn.addEventListener('click', (e) => {
            clipboard(btn.dataset.str);
        });
    }
});