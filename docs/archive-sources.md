# Archive sources beyond the parish books

Where to look when a question goes past the church books (C, A I, B) that
[records.md](records.md) reads. A digest, in our words, of three Riksarkivet
guides; chapter or page numbers point into them. Not validated against the
archives themselves: check present-day names and locations in NAD before
relying on a "kept" column (the administrative handbook predates some
reorganisations).

Sources, from Riksarkivet's public Hugging Face bucket
(`huggingface.co/buckets/Riksarkivet/pdfs`, files listed at
`/api/buckets/Riksarkivet/pdfs/tree`, fetched with `/resolve/<file>`; some
PDFs ship with a ready `.md`):

- *Hur riket styrdes* (administrative history; **HRS**, chapters).
- *Släktforskarna och Krigsarkivet*, January 2026 (**KA**, pages).
- *Ingång till fastighetsforskning*, Riksarkivet i Härnösand 2021 (**FF**).
- Also in the bucket, not digested: *Ingång till samisk historia* (2024),
  *Medeltidens samhälle*.

A text dump of the three lives in `data/cache/riksarkivet-guides/` for grep
(refetchable, not backed up).

## By question

| Question | Record | Producer | Period | Kept |
| --- | --- | --- | --- | --- |
| Who lived and paid tax on which farm? | Mantalslängder | Mantalskommissarie, then häradsskrivare per fögderi | 1640s–1966 | Landsarkiv; the copy sent in to Kammarkollegiet at RA (HRS 5) |
| Who held the farm, at what mantal? | Jordeböcker, taxeringslängder (jordregistret from 1909) | Landskontor, fögderi | 1600s–1917 | Landsarkiv; jordebokssocken can differ from church parish (HRS 5, 8; FF) |
| Earliest local tax | Landskapshandlingar, länsräkenskaper | Fogdar | 1539–1820 | RA, with databases (HRS 5) |
| Court case, dispute, crime | Domböcker, inneliggande handlingar | Häradsrätt (rural), rådhusrätt (town) | to 1970, then tingsrätt | Landsarkiv; fair copies in hovrätt archives without appendices (HRS 7) |
| Estate | Bouppteckningar, own series | Häradsrätt, rådhusrätt | | Landsarkiv; town series fuller (HRS 7) |
| Who owned the property? | see "Property" below | courts, inskrivningsdomare | | (FF) |
| Appeal | Hovrätt records: Svea 1614, Göta 1634, Skåne-Blekinge 1821 | Hovrätt | | Svea at RA; others regional (HRS 7) |
| Imprisoned | Länsfängelse prisoner rolls, photos | Länsstyrelse, fångvårdsstyrelsen 1825– | 1840s– | Landsarkiv, RA (HRS 7) |
| Clergy, visitations, parish reports | Domkapitel archives; herdaminne in print | Stift | 1500s– | Landsarkiv (HRS 8) |
| Parish self-government, poor relief | Sockenstämma, kyrkoråd, fattigvård minutes | Parish; civil kommun from 1863 | 1600s– | Parish archives; kommun's own after 1862 (HRS 8, 11) |
| School | Pupil and teacher registers | Läroverk (state to 1966), folkskola | 1600s– | Landsarkiv (HRS 8) |
| Health | Provinsialläkare, lasarett records | | 1700s– | Landsarkiv; central bodies at RA (HRS 8) |
| Miners, ironworks | Bergmästare, bergsrätt domböcker | Bergsstaten | 1630s–1850s | RA (bergskollegium); local at landsarkiv (HRS 6, 7) |
| Customs, shipping | Tull ledgers | Tullkammare | 1530s– | Central at RA, local poorly kept (HRS 6) |
| Pension | Pension funds (army 1756–), folkpension 1913 | State | | RA (HRS 10) |
| Soldier | see "Soldiers" below | | | Krigsarkivet (KA) |

Dates that move records between archives (HRS): län from 1634–35;
indelningsverket and church bookkeeping from the 1680s; kommunreform 1862–63;
fögderireform 1917–18; häradsskrivare to 1966; tingsrätt from 1971.

## Soldiers (KA)

A household exam usually says only *soldat*, *ryttare* or *båtsman*. The
path:

1. Take the parish he lived in while serving (else birth parish and
   neighbours).
2. Look the parish up in **Grill**, *Statistiskt sammandrag af svenska
   indelningsverket* (1855–58; a database in Digitala forskarsalen). Part I
   cavalry, II infantry, III båtsmän (IV, extra rotering, rarely). The page
   gives regiment (båtsmän: company and station, Karlskrona unless stated)
   and which company the parish's rotar belong to.
3. Open the regiment's **generalmönsterrullor**: by company, then rote
   number. They give soldier name, age, birthplace (province early, date and
   parish from the early 1800s), height, service years, marital state and
   remarks (sick, discharged, died, pension).
4. Then the regimental archive (series D, rolls): the recruitment roll in
   the year of admission gives his civil name and birth; the stamrulla
   (late 1800s) lists every holder of a number.

Pitfalls: company names change with the captain, numbers mostly do not;
the civil patronymic is rare before the mid-1800s, so match on rote number
and period, not soldier name (names recur per rote: our inference);
vargeringsmän share the rote number but have no soldier name; båtsmän have
no continuous roll series (card register in NAD); Finnish units are poorly
preserved (use Finska löneregleringskommittén 1810); after 1901
(värnplikt) you need parish, birth date and the inskrivning number. Family
details are almost never in the rolls. Centrala soldatregistret (a free
web database) helps with basic data.

## Property (FF)

Search backwards from today's fastighetsbeteckning:

- **Fastighetsböcker** 1933–c.1999 (inskrivningsdomare, then
  inskrivningsmyndighet): per parish, alphabetical by property; columns for
  formation, lagfart (owner, date, aktnummer), inteckning. Digitised for
  the whole country, but readable only in RA's reading rooms. Retired pages
  sit apart as *avställda blad*.
- **Lagfartsböcker** and inteckningsböcker c.1875–1933: a reference like
  `XI:244:3` is volume, page, row ("rum"); each row points back to the
  previous owner's row. Partly in Digitala forskarsalen.
- Before 1875: **uppbud** at three successive tings; the fastebrev and its
  basis (köpebrev, bouppteckning) are in the häradsrätt or rådhusrätt
  archive under the date of the first uppbud. Inheritance needed no
  registration until 1876, so use bouppteckningar and household exams.
- Older names: village + number + mantal ("Elgerum nr 4, 1/24 mantal") in
  the country, *stadsäga* numbers in towns.
- Inskrivning archives 1933–2008 are kept for the whole country at RA
  Härnösand; after June 2008 at Lantmäteriet, as are official servitudes.

## Search aids

- NAD (Nationell arkivdatabas): all holdings; its topographic register gives
  a parish's län and fögderi from 1720.
- Riksarkivets beståndsöversikt; *Sveriges församlingar genom tiderna*
  (parish identities); Almquist, *Lagsagor och domsagor* (which court
  served a parish); Wichman's county boundaries in *Mantalslängder
  1642–1820*.
