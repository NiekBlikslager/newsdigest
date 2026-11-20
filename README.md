# Persoonlijke nieuwsdigest

Elke ochtend rond 06:45 (Amsterdamse tijd) een rustige nieuwsmail: grotere verhalen,
onderzoek en achtergrond in plaats van een nieuwsticker. Volledig geautomatiseerd met
GitHub Actions, de Claude API en Resend.

## Hoe het werkt

```
RSS-feeds ──> verzamelen ──> ontdubbelen ──> scoren ──> samenstellen ──> mail
(config/      (laatste 24u,  (zelfde verhaal  (Claude Haiku:  (Claude Sonnet:   (Resend)
 sources.yaml) ma: 72u)       = één groep;     elke kop 0-10   8-12 items,
                              al verstuurd     t.o.v. je       Nederlands,
                              = weg)           profiel)        met bronnen)
```

| Bestand | Wat het doet |
|---|---|
| `config/profile.md` | Jouw interesseprofiel en regels. Gaat letterlijk naar de AI. |
| `config/sources.yaml` | De lijst met feeds (naam, URL, categorie, betaalmuur ja/nee). |
| `config/settings.yaml` | Modelnamen, limieten, tijdvenster, e-mailadres, verzendtijd. |
| `newsdigest/collect.py` | Stap 1: feeds ophalen (een kapotte feed wordt overgeslagen). |
| `newsdigest/dedupe.py` | Stap 2: dubbele verhalen groeperen, al verstuurde verhalen weghalen. |
| `newsdigest/scoring.py` | Stap 3: goedkoop model scoort elke kop. |
| `newsdigest/compose.py` | Stap 4: sterker model schrijft de digest (mag een paar artikelen volledig lezen). |
| `newsdigest/render.py` | HTML-mail en platte-tekstversie. |
| `newsdigest/mailer.py` | Stap 5: versturen via Resend (of SMTP). |
| `newsdigest/state.py` | Onthoudt wat je al kreeg, in `state/state.json`. |
| `.github/workflows/digest.yml` | Het dagelijkse schema. |
| `.github/workflows/check-feeds.yml` | Controleert of alle feeds nog werken. |

**Kosten.** Het scoren van ~300 koppen met Claude Haiku kost minder dan een cent. Het
samenstellen met Claude Sonnet kost naar schatting 8 à 15 cent per dag, dus **ongeveer
€3-4 per maand** (gemeten: ongeveer $0,10 per run met korte items; met alinea's iets meer). Wil je betere teksten, zet dan in `settings.yaml` `compose: claude-opus-5-5`
(ongeveer twee keer zo duur). Harde limieten per run staan onder `limits:`.

---

## Stappenplan

### 1. Anthropic API-sleutel

1. Ga naar <https://platform.claude.com> en maak een account aan (of log in).
2. **Billing**: koop een klein tegoed, bijvoorbeeld $5.
3. **Limits** (Settings → Limits): stel een **maandelijkse bestedingslimiet** in, bijvoorbeeld
   $10. Dan kan het nooit uit de hand lopen.
4. **API Keys** → *Create Key*, naam bijvoorbeeld `newsdigest`. Kopieer de sleutel
   (begint met `sk-ant-`); je ziet hem maar één keer.

### 2. E-mail via Resend

Resend is gratis tot 3.000 mails per maand en heeft geen wachtwoorden of 2FA-gedoe.

1. Maak een account op <https://resend.com> **met het adres waarop je de digest wilt
   ontvangen** (niek@blikslager.com). Zonder eigen domein mag Resend namelijk alleen naar
   dat adres mailen, vanaf `onboarding@resend.dev`. Voor één persoon is dat precies genoeg.
2. **API Keys** → *Create API Key* (rechten: *Sending access*). Kopieer de sleutel (`re_...`).
3. *Optioneel, later:* onder **Domains** `blikslager.com` verifiëren (een paar DNS-records),
   dan kun je in `settings.yaml` een eigen afzender zetten, zoals `digest@blikslager.com`.
   Dat helpt ook tegen de spammap.

<details><summary>Alternatief: Gmail met app-wachtwoord</summary>

1. Zet tweestapsverificatie aan op je Google-account.
2. Maak een app-wachtwoord: <https://myaccount.google.com/apppasswords>.
3. Zet in `config/settings.yaml` `provider: smtp`.
4. Voeg bij stap 3 de secrets `SMTP_USER` (je Gmail-adres) en `SMTP_PASSWORD` (het
   app-wachtwoord) toe in plaats van `RESEND_API_KEY`.
</details>

### 3. GitHub Secrets toevoegen

In deze repository: **Settings → Secrets and variables → Actions → New repository secret**.

| Naam | Waarde |
|---|---|
| `ANTHROPIC_API_KEY` | de sleutel uit stap 1 |
| `RESEND_API_KEY` | de sleutel uit stap 2 |
| `DIGEST_TO` | *optioneel*: ontvangstadres. Overschrijft `settings.yaml`, handig omdat deze repo openbaar is. |

Sleutels komen nooit in de code of in de repository.

### 4. Testen en activeren

1. Ga naar het tabblad **Actions**. Klik zo nodig op *I understand my workflows, go ahead
   and enable them*.
2. Kies **Daily digest** → **Run workflow** → mode **dry-run** → *Run workflow*.
   Na 1-3 minuten staat onderaan de run, onder *Artifacts*, `digest-preview`. Download het
   zip-bestand en open `digest.html` in je browser. Er wordt niets gemaild.
3. Tevreden? Draai hem nog een keer met mode **test**: je krijgt één echte mail met
   `[TEST]` in het onderwerp.
   *Gratis alternatief:* een dry-run bewaart ook `digest.json`. Zet dat bestand in de map
   `samples/` van de repo en kies mode **send-saved** met dat pad: dan wordt precies die
   digest gemaild, zonder nieuwe Claude-kosten. Handig om alleen de opmaak te testen.
4. Klaar. Vanaf nu draait het schema elke ochtend vanzelf.

Werkt het opslaan van de status niet (fout bij *Save state*)? Zet dan onder
**Settings → Actions → General → Workflow permissions** *Read and write permissions* aan.

### Over het tijdstip

GitHub rekent in UTC en kent geen zomer- of wintertijd, en **slaat geplande runs soms
helemaal over**. Daarom start de workflow elk half uur tussen 04:40 en 07:10 UTC. Het
script kijkt zelf hoe laat het in Amsterdam is:

- vóór 06:35 → overslaan (in de wintertijd zijn de eerste runs een uur te vroeg);
- vanaf 06:35 → digest maken en **meteen versturen** zodra hij klaar is (een paar minuten,
  dus meestal rond 06:45). Valt die run uit, dan pakt een volgende run het een half uur
  later op;
- al verstuurd vandaag → overslaan (geen dubbele mails);
- na 10:00 → niet meer versturen.

Een overgeslagen run kost alleen een paar seconden gratis GitHub-tijd. Is er toch niets
gekomen? Start dan *Daily digest* met mode **now**: dat stuurt de echte digest van vandaag
meteen (en niet nog een keer als hij al verstuurd is).

**Let op:** GitHub zet geplande workflows uit als een openbare repo 60 dagen geen activiteit
heeft. Omdat het script elke dag `state/state.json` terugschrijft, gebeurt dat hier niet.

### Als er iets misgaat

- Een feed die faalt, wordt overgeslagen en onderaan de mail genoemd.
- Faalt de hele run, dan krijg je een korte foutmail.
- Is er echt niets relevants, dan krijg je een heel korte mail met die mededeling.
- Faalt meer dan de helft van de feeds, dan wordt dat als fout behandeld.

---

## Aanpassen

**Profiel.** Bewerk `config/profile.md` (kan direct op github.com met het potloodje). De
wijziging geldt vanaf de volgende run.

**Bronnen.** Bewerk `config/sources.yaml`. Na het opslaan draait vanzelf de workflow
**Check feeds**, die laat zien welke feeds werken. Losse URL's uitproberen kan via
*Actions → Check feeds → Run workflow* en de URL's in het veld te plakken.

**Instellingen.** In `config/settings.yaml`: modelnamen (actuele namen:
<https://docs.claude.com/en/docs/about-claude/models/overview>), aantal koppen en items,
minimale score, tijdvenster, verzendtijd.

**Lokaal draaien** (optioneel, Python 3.10+):

```bash
pip install -r requirements.txt
```

```bash
python -m newsdigest --collect-only
```

```bash
ANTHROPIC_API_KEY=sk-ant-... python -m newsdigest --dry-run
```

`--collect-only` haalt alleen feeds op en toont de gegroepeerde verhalen (geen API-sleutel
nodig). `--dry-run` maakt de volledige digest in `output/digest.html` zonder te mailen.
`--test` stuurt één echte testmail. `--send-saved output/digest.json` mailt een bewaarde
digest opnieuw, zonder API-kosten.

## Later uitbreiden: feedback

Nog niet gebouwd, wel voorbereid: elk verhaal heeft een vaste `id`, en `state/state.json`
bewaart per dag welke items (met hun ids) in de digest stonden. Een volgende stap kan zijn:
per item een 👍/👎-link in de mail die (bijvoorbeeld via een GitHub-issue of een klein
formulier) de id terugstuurt, en die voorkeuren als extra context aan `scoring.py` meegeven.
