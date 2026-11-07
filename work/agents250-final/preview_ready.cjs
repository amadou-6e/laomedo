async function waitForPreview(context,base){
 const deadline=Date.now()+90000;
 while(Date.now()<deadline){try{const response=await context.request.get(base,{timeout:1500});if(response.ok())return;}catch{}await new Promise(resolve=>setTimeout(resolve,500));}
 throw Error('Task preview did not become ready; no graph action attempted.');
}
module.exports={waitForPreview};
