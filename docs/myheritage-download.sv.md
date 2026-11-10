# Ladda ned gemensamma segment från MyHeritage

*In English: [myheritage-download.md](myheritage-download.md).*

En lathund för dig som delar dina DNA-matchningar på MyHeritage med
projektet. MyHeritage exporterar inte längre alla matchningar på en gång, så
segmenten hämtas från kromosomläsaren (en-till-många), några valda
matchningar i taget.

## Så här brukar det gå till

För varje testperson (kit):

1. **DNA → DNA-matchningar**, och välj kit i menyn högst upp.
2. **DNA-verktyg → Kromosomläsare**, en-till-många.
3. **Lägg till matchningar**: de du blivit tillfrågad om (ungefär sju per
   omgång).
4. **Ladda ned gemensam DNA-information**: en CSV-fil.
5. Döp om den till `<Testperson> <ÅÅÅÅ-MM-DD> <originalnamn>.csv`, till
   exempel `Anna 2026-11-10 shared_dna_segments.csv`.

Upprepa steg 3–5 för nästa matchningar och sedan för nästa testperson.
Skicka filerna som de är och privat (inte i ett forum), eftersom DNA-uppgifter
är känsliga.

## Bra att veta

- **Ta med samma nyckelmatchningar för alla testpersoner** (till exempel en
  känd kusin på varje sida), så går filerna att jämföra mellan syskon.
- **Öppna och spara inte filen i Excel.** Det kan förstöra å, ä och ö och
  kolumnerna. Skicka den nedladdade filen orörd.
- Rader där matchningen heter **"All selected DNA Matches"** är segment som
  delas med alla valda matchningar samtidigt (triangulerade). Låt dem ligga
  kvar, de läses separat.

## Om något saknas

- **Matchningarna är låsta** (suddiga namn, "Lås upp"): kitet behöver ett
  betalt abonnemang eller en upplåsning innan segmenten går att se och
  ladda ned.
- **Ett kit finns inte i menyn**: det tillhör ett annat konto. Be ägaren
  göra dig till förvaltare (manager) av det, eller ladda ned filerna själv.
- **En matchning går inte att hitta**: sök på namnet den har på MyHeritage,
  som kan skilja sig från namnet i trädet.

Meny- och knappnamnen är skrivna ur minnet och kan ha ändrats. Hur filerna
läses: `myheritage_io.py`.
