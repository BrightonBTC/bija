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
});
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
//            link.removeAttribute("data-reply-submit")
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