const MON={JAN:'01',FEB:'02',MAR:'03',APR:'04',MAY:'05',JUN:'06',JUL:'07',AUG:'08',SEP:'09',OCT:'10',NOV:'11',DEC:'12'};
function day(x){return x.replace(/^(?:(\d{1,2})\s+)?([A-Za-z]{3})\s+(\d{3,4})$/,(m,d,mo,y)=>MON[mo.toUpperCase()]?y+'-'+MON[mo.toUpperCase()]+(d?'-'+d.padStart(2,'0'):''):m)}
function one(x){x=x.trim();let m;
 if(m=x.match(/^(?:BET|FROM)\s+(.+?)\s+(?:AND|TO)\s+(.+)$/i))return one(m[1])+'–'+one(m[2]);
 if(m=x.match(/^(?:ABT|EST|CAL|ABOUT)\.?\s+(.+)$/i))return '~'+day(m[1]);
 if(m=x.match(/^BEF\.?\s+(.+)$/i))return '<'+day(m[1]);
 if(m=x.match(/^AFT\.?\s+(.+)$/i))return '>'+day(m[1]);
 if(m=x.match(/^FROM\s+(.+)$/i))return day(m[1])+'–';
 if(m=x.match(/^TO\s+(.+)$/i))return '–'+day(m[1]);
 return day(x)}
const fmtDate=s=>s?String(s).split(/;\s*/).map(one).join('; '):'';
// a short span in words between two GEDCOM dates, both full days ("barely a
// day", "12 days", "3 months"); '' from two years up or when either date is
// vaguer than a day, where whole years say it
function shortSpan(a,b){const d=x=>{const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(fmtDate(String(x||'')).split('–')[0]);return m&&m.slice(1).map(Number)};
 const p=d(a),q=d(b);if(!p||!q)return '';const n=Math.round((Date.UTC(q[0],q[1]-1,q[2])-Date.UTC(p[0],p[1]-1,p[2]))/864e5);if(n<0)return '';
 if(n<=1)return 'barely a day';if(n<31)return n+' days';const mo=(q[0]-p[0])*12+q[1]-p[1]-(q[2]<p[2]?1:0);
 return mo<24?(mo===1?'a month':mo+' months'):''}