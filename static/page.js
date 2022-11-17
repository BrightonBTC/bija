document.addEventListener("DOMContentLoaded", function () {
    const btn = document.querySelector('#new_post_submit');
    const form = document.querySelector('#new_post_form');

    btn.addEventListener('click', (e) => {
        e.preventDefault();

        const formData = new FormData(form);
        const data = [...formData.entries()];
        const options = {
            method: 'POST',
            body: JSON.stringify(data),
            headers: {
                'Content-Type': 'application/json'
            }
        }
        fetch('/submit_note', options).then(function(response) {
            return response.json();
        }).then(function(response) {
           if(response['event_id']){
               notify('/note?id='+response['event_id'], 'Note created. View now?')
           }
        }).catch(function(err) {
            console.log(err)
        });

        return false;
    });
    if(document.querySelector(".main[data-page='Home']") != null){
        f = new bijaFeed();
    }
    if(document.querySelector(".main[data-page='Profile']") != null){
        console.log("PROFILE ")
        f = new bijaProfile();
    }

});

class bijaProfile{

    constructor(){
        setInterval(getProfileUpdates, 2000);
    }

}

async function getProfileUpdates() {
        const profile_elem = document.querySelector("#profile")
        const pk = profile_elem.dataset.pk
        const updat = profile_elem.dataset.updat
        const response = await fetch('/upd_profile?pk='+pk+'&updat='+updat);
        const d = await response.json();
        if("profile" in d){
            profile = d.profile

            document.querySelector(".profile-about").innerText = profile.about

            document.querySelector("#profile").dataset.updat = profile.updated_at

            const name_els = document.querySelectorAll(".profile-name");
            for (let i = 0; i < name_els.length; i++) {
              name_els[i].innerText = profile.name
            }
            const pic_els = document.querySelectorAll(".profile-pic");
            for (let i = 0; i < pic_els.length; i++) {
              pic_els[i].setAttribute("src", profile.pic)
            }
        }
    }

class bijaFeed{

    constructor(){
        this.data = {};
        this.loading = 0;
        this.listener = () => this.loader(this);
        window.addEventListener('scroll', this.listener);
        this.setClicks()
    }

    setClicks(){
        const links = document.querySelectorAll(".reply-link");
        for (const link of links) {
            link.addEventListener("click", (event)=>{
                event.preventDefault();
                event.stopPropagation();
                let id = link.dataset.rel
                document.querySelector(".reply-form[data-noteid='"+id+"']").style.display = "block"
                return false
            });
        }
        const btns = document.querySelectorAll("input[data-reply-submit]");
        for (const btn of btns) {
            btn.addEventListener("click", (event)=>{
                event.preventDefault();
                event.stopPropagation();
                let id = btn.dataset.rel
                this.postReply(id)
                return false
            });
        }
        const note_links = document.querySelectorAll(".note-content[data-rel]");
        for (const note_link of note_links) {
            note_link.addEventListener("click", (event)=>{
                event.preventDefault();
                event.stopPropagation();
                let id = note_link.dataset.rel
                window.location.href = '/note?id='+id
            });
        }

    }

    loader(o){
        if (
            (window.innerHeight +window.innerHeight + window.scrollY) >= document.body.offsetHeight && o.loading == 0
        ){
            let nodes = document.querySelectorAll('.note[data-dt]')
            o.requestNextPage(nodes[nodes.length-1].dataset.dt);
        }
    }

    setLoadingCompleted(){
        this.loading = 2; // nothing more to load
    }

    requestNextPage(ts){
        this.loading = 1;
        let o = this;
        fetch('/feed?before='+ts, {
            method: 'get'
        }).then(function(response) {
            return response.text();
        }).then(function(response) {
            o.loadArticles(response);
            o.setClicks()
        }).catch(function(err) {
            console.log(err);
        });
    }

    loadArticles(response){
        document.getElementById("main-content").innerHTML += response;
        this.loading = 0;
    }

    postReply(id){
        const form = document.querySelector(".reply-form[data-noteid='"+id+"']")
        const formData = new FormData(form);
        const data = [...formData.entries()];
        const options = {
            method: 'POST',
            body: JSON.stringify(data),
            headers: {
                'Content-Type': 'application/json'
            }
        }
        fetch('/submit_note', options).then(function(response) {
            return response.json();
        }).then(function(response) {
           if(response['event_id']){
               notify('/note?id='+response['event_id'], 'Note created. View now?')
           }
        }).catch(function(err) {
            console.log(err)
        });
    }

}

setInterval(getUpdates, 5000);
async function getUpdates() {
    const response = await fetch('/upd');
    const d = await response.json();
    if("unseen_posts" in d){
    let el_unseen = document.getElementById("n_unseen_posts")
        if(parseInt(d['unseen_posts']) == 0){
            el_unseen.style.display = "none"
        }
        else{
            el_unseen.style.display = "inline-block"
            el_unseen.innerText = d['unseen_posts']
        }
    }
}

let notify = function(link, text){
    n = document.querySelector(".notify")
    if(n !== null) n.remove()
    a = document.createElement("a")
    a.innerText = text
    a.href = link
    document.body.append(a)
    a.classList.add('notify')
    setTimeout(function(){
        d.remove()
    }, 3500);
}