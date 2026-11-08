"""Pluggable avatar sources. Each backend turns a Person into bytes plus a file extension.

procedural   offline SVG, deterministic, free (default)
dicebear     free HTTP API, cartoon styles, seed-based; no era awareness
pollinations free text-to-image URL; uses the era prompt; slow and not deterministic
openai       DALL-E / gpt-image via API key; best quality; costs money
prompt       writes the prompt only, for pasting into any image tool by hand
"""
from __future__ import annotations
import os, urllib.parse, urllib.request
from typing import Protocol
from .person import Person
from . import procedural

ERA_PROMPT = {
    "baroque":   "an 18th-century oil painting portrait, powdered wig or lace bonnet, gilded oval frame",
    "georgian":  "an early-1800s painted miniature portrait, cravat or fichu, gilded oval frame",
    "victorian": "a sepia 1870s cabinet-card studio photograph, high collar, formal pose",
    "early20":   "a black-and-white 1920s family snapshot with a white border",
    "modern":    "a bright modern cartoon profile picture, flat colours",
    "unknown":   "a neutral placeholder silhouette",
}


def build_prompt(p: Person) -> str:
    who = {"M": "man", "F": "woman"}.get(p.sex.upper()[:1], "person")
    where = f" from {p.region}" if p.region else ""
    born = f", born around {p.birth_year}" if p.birth_year else ""
    return (f"Friendly cartoon caricature of a fictional {p.portrait_age}-year-old {who}{where}{born}, "
            f"head and shoulders, styled as {ERA_PROMPT[p.era]}. "
            "Simple shapes, warm expression, no text, no real person's likeness.")


class Backend(Protocol):
    name: str
    version: str
    ext: str
    def generate(self, p: Person) -> bytes: ...


class ProceduralBackend:
    name, version, ext = "procedural", procedural.STYLE_VERSION, "svg"
    def generate(self, p: Person) -> bytes:
        return procedural.render(p).encode()


class DiceBearBackend:
    """https://www.dicebear.com - styles: adventurer, avataaars, big-smile, lorelei, notionists, personas..."""
    ext = "svg"
    def __init__(self, style: str = "adventurer"):
        self.style, self.name, self.version = style, f"dicebear-{style}", f"9.x-{style}"
    def generate(self, p: Person) -> bytes:
        url = f"https://api.dicebear.com/9.x/{self.style}/svg?seed={urllib.parse.quote(p.id)}"
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read()


class PollinationsBackend:
    name, version, ext = "pollinations", "1", "jpg"
    def generate(self, p: Person) -> bytes:
        q = urllib.parse.quote(build_prompt(p))
        url = f"https://image.pollinations.ai/prompt/{q}?width=512&height=512&nologo=true&seed={p.seed() % 2**31}"
        with urllib.request.urlopen(url, timeout=120) as r:
            return r.read()


class OpenAIBackend:
    name, version, ext = "openai", "gpt-image-1", "png"
    def generate(self, p: Person) -> bytes:
        import base64
        from openai import OpenAI          # pip install openai; needs OPENAI_API_KEY
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        res = client.images.generate(model=self.version, prompt=build_prompt(p), size="1024x1024")
        return base64.b64decode(res.data[0].b64_json)


class PromptOnlyBackend:
    name, version, ext = "prompt", "1", "txt"
    def generate(self, p: Person) -> bytes:
        return build_prompt(p).encode()


BACKENDS = {
    "procedural": ProceduralBackend,
    "dicebear": DiceBearBackend,
    "pollinations": PollinationsBackend,
    "openai": OpenAIBackend,
    "prompt": PromptOnlyBackend,
}
