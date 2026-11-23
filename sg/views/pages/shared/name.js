const nm=s=>esc(s).replace(/(\S+)\*/g,'<u>$1</u>');
const pname=(s,unk='')=>!s?'<i class="unk">name unknown</i>':(unk.includes('g')?'<i class="unk">…</i> ':'')+nm(s);
const plainName=s=>s?String(s).replace(/\*/g,''):'name unknown';
// what a person was called: a starred name in brackets (a nickname, "(Betty*)"),
// else the starred given names, else all given names; other brackets are spellings
const callName=s=>{const nick=/\(([^)]*\*)\)/.exec(s||'');if(nick)return nick[1].replace(/\*/g,'');
 const w=String(s||'').replace(/\s*\([^)]*\)/g,'').split(' '),g=w.length>1?w.slice(0,-1):w,st=g.filter(x=>x.endsWith('*'));
 return (st.length?st:g).join(' ').replace(/\*/g,'')};