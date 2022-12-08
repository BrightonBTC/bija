window.addEventListener("load", function () {
    const relay_cbs = document.querySelectorAll(".relay_cb");
    if(relay_cbs.length>0){
        for (var i = 0 ; i < relay_cbs.length; i++){
            relay_cbs[i].addEventListener('click', (e) => {
                const n = n_checked();
                if (n < 2){
                    for (var i = 0 ; i < relay_cbs.length; i++){
                        if(relay_cbs[i].checked){
                            relay_cbs[i].setAttribute("disabled","true")
                        }

                    }
                }
                else{
                    for (var i = 0 ; i < relay_cbs.length; i++){
                        relay_cbs[i].removeAttribute("disabled")
                    }
                }
            });
        }
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