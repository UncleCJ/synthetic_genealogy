# genealogy_avatars

Cartoon "gravatars" for family-tree people and DNA matches. Same person ID gives the same face every time.
The picture's style follows the era: oil portrait (before 1840), sepia cabinet card (1840–1899),
black-and-white snapshot (1900–1944), colour cartoon (1945 onwards), "?" silhouette when nothing is known.

    python -m genealogy_avatars.cli demo                          # fictional 8-generation line
    python -m genealogy_avatars.cli matches segments.csv          # one avatar per MyHeritage match
    python -m genealogy_avatars.cli demo --backend dicebear       # free web API, other cartoon styles
    python -m genealogy_avatars.cli prompts                       # prompts to paste into DALL-E, Gemini etc.

Backends: procedural (offline SVG), dicebear, pollinations (free, AI), openai (needs OPENAI_API_KEY), prompt.
Cache: avatars/<backend>/<id>-<fingerprint>.<ext> + index.json. Put real photos in avatars/override/<id>.jpg to replace any avatar.

In a notebook:

    from genealogy_avatars import Person, render
    from IPython.display import SVG
    SVG(render(Person("I12", "Brita", "F", 1706, 50)))

## Kinship-aware avatars (photos pull on the tree)

    photos/<person_id>/*.jpg  --extract.py-->  identity embedding (512-d) + 9 drawable traits per photo
    pedigree (+ shared cM)    --kinship.py-->  relationship matrix A
    infer.py: K = h2*A + (1-h2)*I, photos = noisy looks  -->  posterior face vector + uncertainty for everyone
    procedural.render(p, traits=to_render(mean), evidence=..., side=...)

    python -m genealogy_avatars.kindemo      # simulated family: hidden truth vs photos vs inferred

extract.py needs `pip install insightface onnxruntime mediapipe==0.10.14 opencv-python` and was not run
where this was written. faces.npz is biometric data about living relatives: keep it local and out of git.

## From your GEDCOM

    python -m genealogy_avatars.dossier tree.ged @I0003@ 5     # 5-generation pedigree page with avatars + sources

gedcom.load() returns people and families with call names (the '*' name), MyHeritage IDs (FACT MH:I123),
citation transcriptions and links (MyHeritage records, Riksarkivet scans, Smart Match profiles).
Indi.to_person() feeds the avatar renderer; father/mother links feed kinship.pedigree_matrix().
