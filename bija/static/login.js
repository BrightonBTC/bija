window.addEventListener("load", function () {
    const pw_form = document.querySelector('.pw_form')
    if(pw_form){
        pw_form.style.display = 'none'
        const setup_btns = document.querySelectorAll('input.setup')
        for(const btn of setup_btns){
            btn.addEventListener("click", (event)=>{
                event.preventDefault();
                event.stopPropagation();
                pw_form.style.display = 'block'
                document.querySelector('.step1').style.display = 'none'
            });
        }
    }
    const inp = document.querySelector('input')
    if(inp){
        inp.focus()
    }

});
const n_checked = function(){
    let n = 0;
    const relay_cbs = document.querySelectorAll(".relay_cb");
    for (var i = 0 ; i < relay_cbs.length; i++){
        if(relay_cbs[i].checked) n++;
    }
    return n
}