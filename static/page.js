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
               window.location.href = '/note?id='+response['event_id']
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

    }

    loader(o){

        console.log((window.innerHeight +window.innerHeight + window.scrollY) + " / " +document.body.offsetHeight + " / " +o.loading)
        if (
            (window.innerHeight +window.innerHeight + window.scrollY) >= document.body.offsetHeight && o.loading == 0
        ){
            console.log("bottom")
            let nodes = document.querySelectorAll('.note[data-dt]')
            o.requestNextPage(nodes[nodes.length-1].dataset.dt);
        }
    }

    setLoadingCompleted(){
        this.loading = 2; // nothing more to laod
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
        }).catch(function(err) {
            console.log(err);
        });
    }

    loadArticles(response){
        document.getElementById("main-content").innerHTML += response;
        this.loading = 0;
    }

    destruct(){
        this.elems = {};
        this.data = {};
        window.removeEventListener("scroll", this.listener);
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