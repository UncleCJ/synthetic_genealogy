// The nav bar carries the focus (roadmap, "Linking"): each page tells
// navFocus what it is on (person: an MH id; parish; code: a lineage code;
// sel, mark: Geography's rules), and the other views' links open there. A
// view that cannot show the focus opens as it is. linkTo(page, focus) is the
// one place each view's address is built from a focus.
const LINKS={
 'family.html':f=>f.person?{p:f.person}:null,
 'geography.html':f=>f.sel||f.mark?{sel:f.sel,mark:f.mark}:f.person?{person:f.person,lines:'1'}:f.parish?{parish:f.parish,kin:'all'}:null,
 'archives.html':f=>f.parish?{parish:f.parish,kin:'all'}:f.person?{person:f.person,kin:'all'}:null,
 'genome.html':f=>f.code?{c:f.code}:null,
 'worklist.html':f=>f.person?{person:f.person}:null};
function linkTo(page,f){const h=LINKS[page]&&LINKS[page](f||{});if(!h)return page;const u=new URLSearchParams();
 for(const [k,v] of Object.entries(h))if(v)u.set(k,v);
 return page+'#'+u.toString().replace(/%3A/g,':').replace(/%2C/g,',').replace(/%40/g,'@').replace(/%7C/g,'|')}
function navFocus(f){document.querySelectorAll('nav.views a').forEach(a=>{const page=a.getAttribute('href').split('#')[0];
 if(page in LINKS&&!a.classList.contains('on'))a.href=linkTo(page,f)})}
