"""Builds the project's web page (GitHub Pages, folder docs/) in English and
Spanish from one template.

    python tools/build_site.py

Ads: the page has a few places for ads, empty until ADSENSE_CLIENT in
docs/ads.js is set (AdSense needs an own domain, not github.io).
"""

import html
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
from usbrescue.brand import APP_NAME, VERSION, donation_url  # noqa: E402

SITE = "https://aluhxp.github.io/unformat-usb/"
REPO = "https://github.com/aluhxp/unformat-usb"
EXE = REPO + "/releases/latest/download/UnformatUSB.exe"
MAC = REPO + "/releases/latest/download/UnformatUSB-macOS.zip"
LINUX = REPO + "/releases/latest/download/UnformatUSB-x86_64.AppImage"
POLICY = REPO + "/blob/main/docs/code-signing.md"

T = {
    "en": dict(
        path="", lang_attr="en",
        title="Unformat USB: recover a USB drive formatted by mistake, free",
        description="Free, open source program that brings back the folders and files of a USB "
                    "drive or memory card formatted by mistake (exFAT, FAT32 and NTFS). No limits, "
                    "never writes to the drive. Windows, macOS and Linux.",
        h1="Formatted your USB drive by mistake?",
        lead="Your files are probably still there. Unformat USB finds them and brings them back "
             "with their folders. <strong>Free, no limits</strong>, and it never writes to the drive.",
        dl_win="Download for Windows", dl_mac="Download for macOS", dl_linux="Linux →",
        dl_note="Version {v} · English, Spanish and Portuguese · not signed yet: Windows may warn you, "
                "choose <em>More info → Run anyway</em>.",
        first_h="First, before anything else",
        first=["<strong>Stop using the drive.</strong> Don't copy anything new onto it: every new "
               "file can cover an old one.",
               "<strong>Don't format it again</strong> and don't let a program “repair” it.",
               "Keep it unplugged until you have the program ready."],
        shot_alt="Unformat USB showing the folders it found on a formatted drive",
        how_h="How it works",
        how=[("Choose the drive", "Only external drives and cards are listed, so you can't pick "
              "your computer's own disk by accident."),
             ("Watch the folders appear", "It shows what it finds while it searches, with a "
              "preview. Tick what you want."),
             ("Rescue", "The files are copied to your computer, never onto the drive itself.")],
        feat_h="What it does",
        feats=[("Rebuilds your folders", "With their original names and contents, including large "
                "videos stored in pieces."),
               ("Free for real", "No 100 MB or 500 MB limit, no trial, no account. Rescue "
                "everything."),
               ("Read-only", "It never writes, repairs or formats the drive, and refuses to save "
                "the rescue onto it."),
               ("Safe mode", "Copies the whole drive to your computer first, then works on the "
                "copy. Best if the drive is failing."),
               ("Loose files too", "Files that were outside any folder come back named after "
                "their content (a photo's date, a document's title)."),
               ("Names lost folders", "Suggests a name for folders that lost theirs. You approve, "
                "and it can be undone."),
               ("Only photos and videos", "One tick, and you get just your pictures and videos, "
                "each in its folder."),
               ("Deleted files too", "Deleted something by mistake, without formatting? It looks "
                "for it in its folder, without touching what is on the drive now."),
               ("Private", "Works offline. Nothing about you or your files is sent anywhere.")],
        shots_h="A look inside",
        shots=[("1-pick", "Choose the drive"), ("5-done", "Done: what came back"),
               ("6-names", "Names for folders that lost theirs")],
        honest_h="When it cannot help",
        honest="To be clear: after a <strong>full format</strong> (it writes zeros everywhere), "
               "after heavy use of the drive since the format, or on an <strong>SSD/NVMe</strong> "
               "(the system erases free space by itself), there may be nothing left. "
               "Unformat USB tells you so instead of promising what it cannot do. It supports "
               "<strong>exFAT</strong>, <strong>FAT32</strong> and <strong>NTFS</strong>, the "
               "formats of almost every USB drive and memory card.",
        faq_h="Questions",
        faq=[("Can I recover files after formatting a USB drive?",
              "Usually yes. A quick format, the default on Windows, macOS and Linux, only wipes "
              "the index of the drive. The files stay where they were until something new is "
              "written over them."),
             ("Is it really free?",
              "Yes. No limits, no trial, no ads in the program. It is open source (GPL-3.0). If it "
              "helps you, you can buy us a coffee, but you don't have to."),
             ("Does it work with SD and microSD cards?",
              "Yes, with any card or USB drive formatted as exFAT, FAT32 or NTFS, through a card reader "
              "or adapter."),
             ("Can it damage my drive?",
              "No. It only reads. It never writes, repairs or formats the drive, and it won't save "
              "the rescued files onto the same drive."),
             ("Why does Windows ask for administrator rights?",
              "Reading a whole drive, below its files, needs them. That is the only reason."),
             ("Windows says “Windows protected your PC”. Is it safe?",
              "The program is not signed yet (a certificate is on the way). Choose “More info” "
              "and “Run anyway”. The source code is public and every version is built and tested "
              "automatically on GitHub.")],
        donate_h="Did it help?",
        donate="Unformat USB is free and will stay free. If it brought your files back, you can "
               "buy us a coffee.",
        donate_btn="Donate with PayPal",
        foot_src="Source code", foot_policy="Code signing policy and privacy",
        foot_license="License GPL-3.0",
        ad="Advertisement",
    ),
    "es": dict(
        path="es/", lang_attr="es",
        title="Unformat USB: recuperar un pendrive formateado por error, gratis",
        description="Programa gratuito y de código abierto que recupera las carpetas y archivos "
                    "de un pendrive o tarjeta de memoria formateada por error (exFAT, FAT32 y NTFS). Sin "
                    "límites y sin escribir nada en la unidad. Windows, macOS y Linux.",
        h1="¿Formateaste tu pendrive por error?",
        lead="Lo más probable es que tus archivos sigan ahí. Unformat USB los encuentra y los "
             "recupera con sus carpetas. <strong>Gratis, sin límites</strong>, y nunca escribe "
             "nada en la unidad.",
        dl_win="Descargar para Windows", dl_mac="Descargar para macOS", dl_linux="Linux →",
        dl_note="Versión {v} · español, inglés y portugués · aún sin firmar: Windows puede mostrar un aviso, "
                "elige <em>Más información → Ejecutar de todas formas</em>.",
        first_h="Primero, antes que nada",
        first=["<strong>Deja de usar el pendrive.</strong> No copies nada nuevo: cada archivo "
               "nuevo puede tapar uno antiguo.",
               "<strong>No lo vuelvas a formatear</strong> ni dejes que un programa lo “repare”.",
               "Déjalo desconectado hasta tener el programa listo."],
        shot_alt="Unformat USB mostrando las carpetas encontradas en un pendrive formateado",
        how_h="Cómo funciona",
        how=[("Elige el pendrive", "Solo aparecen unidades externas y tarjetas, así no eliges "
              "por error el disco de tu computadora."),
             ("Mira aparecer tus carpetas", "Muestra lo que encuentra mientras busca, con vista "
              "previa. Marca lo que quieres."),
             ("Rescata", "Los archivos se copian a tu computadora, nunca al mismo pendrive.")],
        feat_h="Qué hace",
        feats=[("Reconstruye tus carpetas", "Con sus nombres y contenido originales, incluidos "
                "videos grandes guardados en pedazos."),
               ("Gratis de verdad", "Sin límite de 100 MB o 500 MB, sin prueba, sin cuenta. "
                "Recupera todo."),
               ("Solo lectura", "Nunca escribe, repara ni formatea la unidad, y no deja guardar "
                "el rescate en ella."),
               ("Modo seguro", "Primero copia todo el pendrive a tu computadora y trabaja sobre "
                "la copia. Ideal si la unidad está fallando."),
               ("También archivos sueltos", "Los que estaban fuera de las carpetas vuelven con "
                "un nombre según su contenido (la fecha de una foto, el título de un documento)."),
               ("Nombra carpetas perdidas", "Sugiere un nombre para las carpetas que perdieron "
                "el suyo. Tú apruebas, y se puede deshacer."),
               ("Solo fotos y videos", "Con una marca, recuperas solo tus fotos y videos, cada "
                "uno en su carpeta."),
               ("También archivos borrados", "¿Borraste algo por error, sin formatear? Lo busca "
                "en su carpeta, sin tocar lo que hay ahora en el pendrive."),
               ("Privado", "Funciona sin internet. No envía nada sobre ti ni tus archivos.")],
        shots_h="Por dentro",
        shots=[("1-pick", "Elige el pendrive"), ("5-done", "Listo: lo que volvió"),
               ("6-names", "Nombres para carpetas que perdieron el suyo")],
        honest_h="Cuándo no puede ayudar",
        honest="Para ser claros: después de un <strong>formateo completo</strong> (escribe ceros "
               "en todo), de usar mucho el pendrive tras formatearlo, o en un "
               "<strong>SSD/NVMe</strong> (el sistema borra solo el espacio libre), puede que no "
               "quede nada. Unformat USB te lo dice en vez de prometer lo que no puede. Funciona "
               "con <strong>exFAT</strong>, <strong>FAT32</strong> y <strong>NTFS</strong>, los "
               "formatos de casi todos los pendrives y tarjetas.",
        faq_h="Preguntas",
        faq=[("¿Se pueden recuperar archivos después de formatear un pendrive?",
              "Normalmente sí. Un formateo rápido, el que hacen por defecto Windows, macOS y "
              "Linux, solo borra el índice. Los archivos siguen en su lugar hasta que se escribe "
              "algo nuevo encima."),
             ("¿De verdad es gratis?",
              "Sí. Sin límites, sin prueba, sin anuncios en el programa. Es código abierto "
              "(GPL-3.0). Si te ayuda, puedes invitarnos un café, pero no es obligatorio."),
             ("¿Funciona con tarjetas SD y microSD?",
              "Sí, con cualquier tarjeta o pendrive en exFAT, FAT32 o NTFS, usando un lector o "
              "adaptador."),
             ("¿Puede dañar mi pendrive?",
              "No. Solo lee. Nunca escribe, repara ni formatea la unidad, y no guarda los "
              "archivos rescatados en el mismo pendrive."),
             ("¿Por qué Windows pide permisos de administrador?",
              "Para leer la unidad completa, por debajo de sus archivos, hacen falta. Es la única "
              "razón."),
             ("Windows dice “Windows protegió su PC”. ¿Es seguro?",
              "El programa todavía no está firmado (el certificado está en trámite). Elige “Más "
              "información” y “Ejecutar de todas formas”. El código es público y cada versión se "
              "compila y prueba automáticamente en GitHub.")],
        donate_h="¿Te sirvió?",
        donate="Unformat USB es gratis y lo va a seguir siendo. Si recuperó tus archivos, puedes "
               "invitarnos un café.",
        donate_btn="Donar con PayPal",
        foot_src="Código fuente", foot_policy="Política de firma de código y privacidad",
        foot_license="Licencia GPL-3.0",
        ad="Publicidad",
    ),
    "pt": dict(
        path="pt/", lang_attr="pt-BR",
        title="Unformat USB: recuperar um pendrive formatado por engano, grátis",
        description="Programa grátis e de código aberto que recupera as pastas e arquivos de um "
                    "pendrive ou cartão de memória formatado por engano (exFAT, FAT32 e NTFS). Sem "
                    "limites e sem gravar nada no pendrive. Windows, macOS e Linux.",
        h1="Formatou seu pendrive por engano?",
        lead="Provavelmente seus arquivos ainda estão aí. O Unformat USB encontra e recupera "
             "tudo com as pastas. <strong>Grátis, sem limites</strong>, e nunca grava nada no "
             "pendrive.",
        dl_win="Baixar para Windows", dl_mac="Baixar para macOS", dl_linux="Linux →",
        dl_note="Versão {v} · português, espanhol e inglês · ainda sem assinatura: o Windows "
                "pode mostrar um aviso, escolha <em>Mais informações → Executar assim mesmo</em>.",
        first_h="Primeiro, antes de tudo",
        first=["<strong>Pare de usar o pendrive.</strong> Não copie nada novo: cada arquivo "
               "novo pode cobrir um antigo.",
               "<strong>Não formate de novo</strong> e não deixe um programa “consertar” o pendrive.",
               "Deixe desconectado até ter o programa pronto."],
        shot_alt="Unformat USB mostrando as pastas encontradas em um pendrive formatado",
        how_h="Como funciona",
        how=[("Escolha o pendrive", "Só aparecem pendrives e cartões externos, assim você não "
              "escolhe o disco do computador por engano."),
             ("Veja as pastas aparecerem", "Mostra o que encontra enquanto procura, com prévia. "
              "Marque o que quiser."),
             ("Resgate", "Os arquivos são copiados para o seu computador, nunca para o próprio "
              "pendrive.")],
        feat_h="O que ele faz",
        feats=[("Reconstrói suas pastas", "Com nomes e conteúdo originais, incluindo vídeos "
                "grandes guardados em pedaços."),
               ("Grátis de verdade", "Sem limite de 100 MB ou 500 MB, sem teste, sem conta. "
                "Recupere tudo."),
               ("Só leitura", "Nunca grava, conserta ou formata o pendrive, e não deixa salvar o "
                "resgate nele."),
               ("Modo seguro", "Primeiro copia o pendrive inteiro para o computador e trabalha "
                "na cópia. Ideal se o pendrive estiver falhando."),
               ("Arquivos soltos também", "Os que estavam fora das pastas voltam com nome pelo "
                "conteúdo (a data de uma foto, o título de um documento)."),
               ("Dá nome a pastas perdidas", "Sugere um nome para as pastas que perderam o seu. "
                "Você aprova, e dá para desfazer."),
               ("Só fotos e vídeos", "Com uma marca, você recupera só suas fotos e vídeos, cada "
                "um na sua pasta."),
               ("Arquivos apagados também", "Apagou algo por engano, sem formatar? Ele procura "
                "na pasta, sem mexer no que está no pendrive agora."),
               ("Privado", "Funciona sem internet. Não envia nada sobre você ou seus arquivos.")],
        shots_h="Por dentro",
        shots=[("1-pick", "Escolha o pendrive"), ("5-done", "Pronto: o que voltou"),
               ("6-names", "Nomes para pastas que perderam o seu")],
        honest_h="Quando não dá para ajudar",
        honest="Para ser claro: depois de uma <strong>formatação completa</strong> (grava zeros "
               "em tudo), de muito uso do pendrive depois de formatar, ou em um "
               "<strong>SSD/NVMe</strong> (o sistema apaga sozinho o espaço livre), pode não "
               "sobrar nada. O Unformat USB avisa em vez de prometer o que não pode. Funciona "
               "com <strong>exFAT</strong>, <strong>FAT32</strong> e <strong>NTFS</strong>, os "
               "formatos de quase todos os pendrives e cartões.",
        faq_h="Perguntas",
        faq=[("Dá para recuperar arquivos depois de formatar um pendrive?",
              "Normalmente sim. A formatação rápida, a padrão do Windows, macOS e Linux, só apaga "
              "o índice. Os arquivos continuam no lugar até algo novo ser gravado por cima."),
             ("É grátis mesmo?",
              "Sim. Sem limites, sem teste, sem anúncios no programa. É código aberto (GPL-3.0). "
              "Se ajudar, você pode pagar um café para a gente, mas não é obrigatório."),
             ("Funciona com cartões SD e microSD?",
              "Sim, com qualquer cartão ou pendrive em exFAT, FAT32 ou NTFS, usando um leitor ou "
              "adaptador."),
             ("Pode danificar meu pendrive?",
              "Não. Ele só lê. Nunca grava, conserta ou formata o pendrive, e não salva os "
              "arquivos resgatados no mesmo pendrive."),
             ("Por que o Windows pede permissão de administrador?",
              "Para ler o pendrive inteiro, por baixo dos arquivos, é preciso. É o único motivo."),
             ("O Windows diz “O Windows protegeu o computador”. É seguro?",
              "O programa ainda não tem assinatura (o certificado está a caminho). Escolha “Mais "
              "informações” e “Executar assim mesmo”. O código é público e cada versão é "
              "compilada e testada automaticamente no GitHub.")],
        donate_h="Ajudou?",
        donate="O Unformat USB é grátis e vai continuar assim. Se recuperou seus arquivos, você "
               "pode pagar um café para a gente.",
        donate_btn="Doar com PayPal",
        foot_src="Código-fonte", foot_policy="Política de assinatura de código e privacidade",
        foot_license="Licença GPL-3.0",
        ad="Publicidade",
    ),
}

MASCOT = """<svg class="mascot" viewBox="0 0 64 76" aria-hidden="true">
<rect x="20" y="0" width="24" height="18" rx="3" fill="#B9C9C2"/>
<rect x="4" y="14" width="56" height="58" rx="16" fill="#FFC857"/>
<rect x="18" y="36" width="8" height="5" rx="2.5" fill="#17302B"/>
<rect x="38" y="36" width="8" height="5" rx="2.5" fill="#17302B"/>
<path d="M22 50h20a3 3 0 0 1 3 3c0 5-6 9-13 9s-13-4-13-9a3 3 0 0 1 3-3z" fill="#17302B"/>
</svg>"""


def ad(t, slot):
    return f'<aside class="ad" data-ad-slot="{slot}" aria-label="{t["ad"]}"></aside>'


def page(lang):
    t = T[lang]
    up = "../" if t["path"] else ""
    img = f"{up}img/{lang}"
    url = SITE + t["path"]
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
        for q, a in t["faq"]]}
    app_ld = {"@context": "https://schema.org", "@type": "SoftwareApplication",
              "name": APP_NAME, "softwareVersion": VERSION, "applicationCategory": "UtilitiesApplication",
              "operatingSystem": "Windows, macOS, Linux", "description": t["description"],
              "url": url, "downloadUrl": EXE, "license": "https://www.gnu.org/licenses/gpl-3.0.html",
              "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}}
    names = {"en": "English", "es": "Español", "pt": "Português"}
    langs = "".join(f'<a class="lang" href="{up}{T[o]["path"]}" hreflang="{T[o]["lang_attr"]}" '
                    f'lang="{T[o]["lang_attr"]}">{names[o]}</a>' for o in T if o != lang)
    first = "".join(f"<li>{x}</li>" for x in t["first"])
    how = "".join(f'<li><span class="n">{i}</span><h3>{h}</h3><p>{p}</p></li>'
                  for i, (h, p) in enumerate(t["how"], 1))
    feats = "".join(f"<li><h3>{h}</h3><p>{p}</p></li>" for h, p in t["feats"])
    shots = "".join(f'<figure><picture><source srcset="{up}img/en_dark/{n}.png" '
                    f'media="(prefers-color-scheme: dark)"><img src="{img}/{n}.png" alt="{c}" '
                    f'width="960" height="640" loading="lazy"></picture><figcaption>{c}</figcaption></figure>'
                    for n, c in t["shots"]) if lang == "en" else "".join(
                    f'<figure><img src="{img}/{n}.png" alt="{c}" width="960" height="640" '
                    f'loading="lazy"><figcaption>{c}</figcaption></figure>' for n, c in t["shots"])
    faq = "".join(f"<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>"
                  for q, a in t["faq"])
    return f"""<!doctype html>
<html lang="{t['lang_attr']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t['title']}</title>
<meta name="description" content="{t['description']}">
<link rel="canonical" href="{url}">
<link rel="alternate" hreflang="en" href="{SITE}">
<link rel="alternate" hreflang="es" href="{SITE}es/">
<link rel="alternate" hreflang="pt-BR" href="{SITE}pt/">
<link rel="alternate" hreflang="x-default" href="{SITE}">
<meta property="og:type" content="website">
<meta property="og:title" content="{t['title']}">
<meta property="og:description" content="{t['description']}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}img/{lang}/3-tree.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#147A5E">
<link rel="icon" href="{up}icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{up}style.css">
<script type="application/ld+json">{json.dumps(app_ld, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(faq_ld, ensure_ascii=False)}</script>
<script src="{up}ads.js" defer></script>
</head>
<body>
<header class="top wrap">
  <a class="brand" href="{url}">{MASCOT}<span>{APP_NAME}</span></a>
  <nav class="langs">{langs}</nav>
</header>
<main>
<section class="hero wrap">
  <div class="hero-text">
    <h1>{t['h1']}</h1>
    <p class="lead">{t['lead']}</p>
    <div class="dl">
      <a class="btn primary" href="{EXE}" data-os="win">{t['dl_win']}</a>
      <a class="btn" href="{MAC}" data-os="mac">{t['dl_mac']}</a>
    </div>
    <p class="note">{t['dl_note'].format(v=VERSION)} <a class="linux" href="{LINUX}">{t['dl_linux']}</a></p>
  </div>
  <picture class="hero-shot">
    <source srcset="{up}img/en_dark/3-tree.png" media="(prefers-color-scheme: dark)">
    <img src="{img}/3-tree.png" alt="{t['shot_alt']}" width="960" height="640">
  </picture>
</section>

<section class="wrap first">
  <h2>{t['first_h']}</h2>
  <ol>{first}</ol>
</section>

<section class="wrap">
  <h2>{t['how_h']}</h2>
  <ol class="how">{how}</ol>
</section>

{ad(t, "after-how")}

<section class="wrap">
  <h2>{t['feat_h']}</h2>
  <ul class="feats">{feats}</ul>
</section>

<section class="wrap">
  <h2>{t['shots_h']}</h2>
  <div class="shots">{shots}</div>
</section>

<section class="wrap honest">
  <h2>{t['honest_h']}</h2>
  <p>{t['honest']}</p>
</section>

{ad(t, "before-faq")}

<section class="wrap faq">
  <h2>{t['faq_h']}</h2>
  {faq}
</section>

<section class="wrap donate">
  <div>
    <h2>{t['donate_h']}</h2>
    <p>{t['donate']}</p>
  </div>
  <a class="btn sun" href="{html.escape(donation_url())}" rel="noopener">{t['donate_btn']}</a>
</section>

{ad(t, "bottom")}
</main>
<footer class="wrap foot">
  <a href="{REPO}">{t['foot_src']}</a>
  <a href="{POLICY}">{t['foot_policy']}</a>
  <a href="{REPO}/blob/main/LICENSE">{t['foot_license']}</a>
</footer>
<script>
// put the button for the visitor's system first
(function () {{
  var mac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  if (!mac) return;
  var dl = document.querySelector('.dl'), m = dl.querySelector('[data-os=mac]'), w = dl.querySelector('[data-os=win]');
  m.classList.add('primary'); w.classList.remove('primary'); dl.insertBefore(m, w);
}})();
</script>
</body>
</html>
"""


def main():
    docs = os.path.join(ROOT, "docs")
    shots = sys.argv[1] if len(sys.argv) > 1 else None
    if shots:   # folder made by tools/screens.py: en/, en_dark/, es/, pt/
        for sub in ("en", "en_dark", "es", "pt"):
            out = os.path.join(docs, "img", sub)
            os.makedirs(out, exist_ok=True)
            for name in ("1-pick", "3-tree", "5-done", "6-names"):
                shutil.copy(os.path.join(shots, sub, name + ".png"), out)
    for lang in T:
        folder = os.path.join(docs, T[lang]["path"])
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(page(lang))
    urls = "".join(f"  <url><loc>{SITE}{T[x]['path']}</loc></url>\n" for x in T)
    with open(os.path.join(docs, "sitemap.xml"), "w") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n")
    with open(os.path.join(docs, "robots.txt"), "w") as fh:
        fh.write(f"User-agent: *\nAllow: /\nSitemap: {SITE}sitemap.xml\n")
    with open(os.path.join(docs, "icon.svg"), "w") as fh:
        fh.write(MASCOT.replace(' class="mascot"', ' xmlns="http://www.w3.org/2000/svg"')
                 .replace(' aria-hidden="true"', ""))
    open(os.path.join(docs, ".nojekyll"), "w").close()


if __name__ == "__main__":
    main()
