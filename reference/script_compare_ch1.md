# Script comparison — gold (hand-written) vs generated

Gold: `reference/ch1_gold_script.md` · Candidate: `projects/solo-leveling-ch1/script.json`

## Metrics (the target is the GOLD column, not 'better than last run')

| metric | gold | candidate |
|---|---|---|
| beats | 17 | 18 |
| words | 677 | 700 |
| avg_sentence_words | 15.0 | 14.0 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 3.25 | 2.57 |
| connectives_per_100w | 3.69 | 3.14 |
| max_consecutive_pronoun_starts | 2 | 1 |
| pronoun_start_fraction | 0.2 | 0.16 |

## Side by side

### Beat 1

**GOLD** (p0002_01, p0003_01, p0004_01, p0005_01, p0006_01):
> Sung Jin-Woo lies in a pool of his own blood, barely able to move. Three towering, glowing-eyed guardians close in on him, weapons raised. A voice brands him the weakest hunter alive. He refuses to believe it, even as the blade comes down again.

**GEN** (p0002_01, p0003_01, p0004_01):
> Sung Jin-Woo, the world's weakest hunter, lies in a pool of his own blood. Giant stone statues with glowing blue eyes tower over him while he struggles to breathe. He admits that he never expected this fate to befall him.

### Beat 2

**GOLD** (p0007_04):
> Then the sky clears, over present-day Seoul.

**GEN** (p0005_01, p0006_01, p0007_01, p0007_04):
> A towering shadow raises a spear to finish him as he clenches his teeth in agony. That is where this day is headed — but it starts hours earlier. The blood-soaked nightmare dissolves into a bright morning in Seoul, where the sky remains clear.

### Beat 3

**GOLD** (p0008_01, p0008_02):
> Jin-Woo walks the morning streets with fresh bandages on his face, just another commuter nobody looks at twice.

**GEN** (p0008_01, p0008_02, p0009_01, p0009_02):
> He walks through a busy urban street, blending in with the crowd despite his facial bandages. Other pedestrians pass him by without a second glance as he quietly makes his way forward. This dangerous line of work constantly puts his very life on the line. Farther down the road, a construction site in Seoul glows with mysterious blue lights.

### Beat 4

**GOLD** (p0009_01, p0009_02):
> Hunting is a job where your life is on the line, and today is a work day. A gate has torn open inside a construction site across town, and hunters are already gathering at the barriers.

**GEN** (p0010_01, p0010_03, p0010_04, p0011_01, p0011_02):
> A blue light pulses behind the construction scaffolding as the dungeon gate rumbles to life. Hunters gather around a nearby food truck, desperate to earn guild money for mounting medical bills. The truck vendor hands a warm drink to Kim Sangshik, a veteran hunter, wishing him luck today. Kim thanks the worker and finishes his quick meal. But as he holds his cup, a voice suddenly calls out his name from across the busy site.

### Beat 5

**GOLD** (p0010_01, p0010_03):
> Inside the scaffolding, the gate hangs glowing blue. At the food truck below, Jin-Woo runs the same math as always — his mother's hospital bills against what the guild pays him.

**GEN** (p0012_01, p0012_02, p0012_03):
> Bak, a former hunter returning to active duty, arrives with a cheerful wave and a handshake. He explains to Kim Sangshik that he is back because his wife is pregnant with their second son. Kim remarks that earning a fortune is never easy.

### Beat 6

**GOLD** (p0010_04, p0011_01):
> The truck sends a hunter off with a wish of luck for the raid, while two more grab a quick meal before heading in.

**GEN** (p0013_01, p0013_02):
> Bak sighs and admits that his situation worsened after taking a break. Kim Sangshik sips his drink while greeting Jin-Woo and thanking him for arriving.

### Beat 7

**GOLD** (p0011_02, p0012_01, p0012_02, p0012_03):
> Song Chi-yul, a veteran of these raids, calls a greeting over his cup. Then an old friend appears — Bak, all smiles in his green puffer jacket. They shake hands, and Bak laughs that he only quit hunting because his wife is expecting their second son. Chi-yul admits that raiding for a fortune, like life itself, was never easy.

**GEN** (p0014_01, p0014_02, p0014_03):
> Jin-Woo weaves through the crowd while a veteran hunter pats his shoulder and remarks on the cold. Kim Sangshik waves and asks if he has eaten. A bystander with dark curly hair wonders if he is secretly powerful.

### Beat 8

**GOLD** (p0013_01, p0013_02, p0014_01):
> Bak just sighs at that. Then the group perks up — Jin-Woo has arrived, and they thank him for coming. A colleague claps his shoulder about the cold, and he tells them he'll pull his weight again today.

**GEN** (p0015_01, p0015_02):
> Bak points at the departing Jin-Woo while Kim Sangshik grins, explaining to the curious bystander that his nickname is the world's weakest.

### Beat 9

**GOLD** (p0014_02, p0014_03):
> The truck regulars ask if he's even eaten yet — everyone is glad to see him. Watching all this warmth, Bak asks the obvious question: is this guy some kind of powerful hunter?

**GEN** (p0016_01, p0016_02, p0016_03):
> Jin-Woo walks past heavy machinery while Kim Sangshik and Bak gossip about his reputation. Bak asks if he is truly the world's weakest, and Kim confirms he is the weakest of them all. Overhearing their laughter, he sighs.

### Beat 10

**GOLD** (p0015_01, p0015_02, p0016_01, p0016_02, p0016_03):
> Another hunter sets him straight — Bak wouldn't know the nickname, since Jin-Woo joined right after he quit. Within earshot, the older hunters trade it like gossip: the weakest hunter in the guild. One asks if he's really the weakest; the other says he is, and that their dungeon must be a weak one since he was assigned to it. Then they hush each other, in case he can hear.

**GEN** (p0017_01, p0017_02):
> He leaves the laughing hunters to ask a stall guard for coffee. The worker apologizes and admits they are out, which only adds to his growing disappointment.

### Beat 11

**GOLD** (p0017_01, p0017_02):
> He hears every word of it, and lets it pass. At the supply stand he asks for a cup of coffee, and the attendant apologizes — they've just run out.

**GEN** (p0018_02, p0018_03, p0018_04):
> He reflects on his miserable luck as even a simple cup of coffee remains out of reach. After he dismisses a gate guard’s concern with a tired wave, a familiar voice suddenly shouts that he is already injured again.

### Beat 12

**GOLD** (p0018_02, p0018_03):
> Not even coffee today, he mutters — it feels like a bad sign. The attendant apologizes again, and he waves it off as nothing.

**GEN** (p0019_01, p0020_01, p0020_03):
> Lee Joo-hee, the party's rookie healer, shouts in frustration and asks why he is injured again. Jin-Woo rubs his neck with an awkward smile. He admits that he was the only hunter hurt during the entire raid.

### Beat 13

**GOLD** (p0018_04, p0019_01, p0020_01):
> Lee Joo-hee, the party's healer, spots him across the lot and comes running — he's hurt again, she says, alarmed. He laughs it off, but she isn't buying it, and asks why his face keeps getting hurt.

**GEN** (p0020_02, p0021_01):
> Lee Joo-hee asks if he visited the hospital, which Jin-Woo confirms. He explains the previous raid members were too arrogant to include a healer.

### Beat 14

**GOLD** (p0020_02, p0020_03, p0021_01):
> They sit together on a stack of lumber while she asks if he actually saw a doctor this time. He admits he did. Joo-hee is stunned to learn he was the only one on his last team who got hurt at all.

**GEN** (p0021_02, p0022_01, p0022_02):
> Lee Joo-hee questions the reckless pride of hunters who skip a healer just to feel safe. Jin-Woo only replies with a melancholic smile, admitting his weakness makes these injuries routine. This admission leaves her sinking into a somber silence.

### Beat 15

**GOLD** (p0021_02, p0022_01, p0022_02, p0022_03):
> The rest of his party outranked him badly enough that they skipped bringing a healer at all, he explains. Joo-hee asks why that would matter, if it's only their own safety they cared about. He shrugs it off with a tired smile. It's only because he's weak, he says, and he's used to it by now. She goes quiet, and the two of them head back toward the group.

**GEN** (p0022_03, p0022_04, p0023_01):
> Jin-Woo stands up and walks toward the massive, glowing blue energy gate. Song Chi-yul, an experienced, high-ranking hunter chosen to lead the dungeon raid, addresses the assembled hunters to volunteer as the party leader.

### Beat 16

**GOLD** (p0022_04, p0023_01, p0024_01, p0024_02):
> The full party gathers at the gate as Chi-yul modestly asks the group to let him lead the raid. The others back him without hesitation — he's the highest-ranked among them, one says, and worth trusting. Jin-Woo and Joo-hee greet him and ask him to look after the group.

**GEN** (p0024_01, p0024_02, p0024_03):
> Kim Sangshik readily agrees that the senior hunter should lead their raid. Bak concurs because he fully trusts the veteran's seasoned skills. Nearby, a hunter in a green jacket shouts his own enthusiastic approval of the plan. Jin-Woo smiles and asks Song Chi-yul to take care of them today.

### Beat 17

**GOLD** (p0024_03, p0025_01, p0026_01, p0026_02, p0026_03, p0027_01):
> Chi-yul tells the group to head in, and they answer eager and ready. He promises to keep the injured Jin-Woo safely behind the front line, and Jin-Woo laughs along, no argument left in him. Kim Sang-shik scowls, uneasy, as they near the entrance. Someone calls Jin-Woo forward — okay, okay, he says — and he steps into the blinding blue light of the gate, and disappears.

**GEN** (p0025_01, p0026_01, p0026_02):
> The raid leader gives the signal, prompting the eager hunters to march toward the glowing blue dungeon gate. Kim Sangshik flashes a reassuring grin at Jin-Woo. Soon, he steps through the swirling portal alongside Lee Joo-hee, the party's rookie healer.

### Beat 18

**GOLD** ():
> (no gold beat)

**GEN** (p0026_03, p0027_01):
> He takes a deep breath to steady his nerves before the plunge. Then, the brilliant blue energy of the gate completely engulfs him as he steps through.
