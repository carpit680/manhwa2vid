# Script comparison — gold (hand-written) vs generated

Gold: `reference/ch1_gold_script.md` · Candidate: `projects/solo-leveling-ch1/script.json`

## Metrics (the target is the GOLD column, not 'better than last run')

| metric | gold | candidate |
|---|---|---|
| beats | 17 | 18 |
| words | 677 | 655 |
| avg_sentence_words | 15.0 | 12.8 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 3.25 | 3.36 |
| connectives_per_100w | 3.69 | 3.21 |
| max_consecutive_pronoun_starts | 2 | 2 |
| pronoun_start_fraction | 0.2 | 0.37 |

## Side by side

### Beat 1

**GOLD** (p0002_01, p0003_01, p0004_01, p0005_01, p0006_01):
> Sung Jin-Woo lies in a pool of his own blood, barely able to move. Three towering, glowing-eyed guardians close in on him, weapons raised. A voice brands him the weakest hunter alive. He refuses to believe it, even as the blade comes down again.

**GEN** (p0002_01, p0003_01, p0004_01):
> Sung Jin-Woo lies bleeding on the cold ground as his life slowly slips away. As an E-Rank hunter for the Hunter Guild, he possesses the lowest rank of magical power.

### Beat 2

**GOLD** (p0007_04):
> Then the sky clears, over present-day Seoul.

**GEN** (p0005_01, p0006_01, p0007_01, p0007_04):
> He gasps for air in sheer desperation. Above him, the sentinel raises its spear to strike. He curses in agony as the heavy stone weapon drives downward. A blinding flash of white light suddenly consumes the space. Then the sky clears, over present-day Seoul.

### Beat 3

**GOLD** (p0008_01, p0008_02):
> Jin-Woo walks the morning streets with fresh bandages on his face, just another commuter nobody looks at twice.

**GEN** (p0008_01, p0008_02, p0009_01):
> He crosses a busy street in Seoul, blending into the morning crowd. He admits that hunting is a profession where his life stays constantly on the line.

### Beat 4

**GOLD** (p0009_01, p0009_02):
> Hunting is a job where your life is on the line, and today is a work day. A gate has torn open inside a construction site across town, and hunters are already gathering at the barriers.

**GEN** (p0009_02, p0010_01, p0010_03, p0010_04, p0011_01, p0011_02):
> At a dark Seoul construction site, Jin-Woo watches a magical Gate vibrate with energy behind heavy scaffolding. He relies on his raid payouts to cover his sick mother's rising medical bills. Nearby, Kim Sangshik, a supporting hunter, leans against a food truck while waiting for the mission. The KHA vendor hands him a warm drink and wishes him luck on his raid. Kim replies with a quick word of thanks and takes his cup from the counter. But he pauses in surprise when a loud voice calls out his name.

### Beat 5

**GOLD** (p0010_01, p0010_03):
> Inside the scaffolding, the gate hangs glowing blue. At the food truck below, Jin-Woo runs the same math as always — his mother's hospital bills against what the guild pays him.

**GEN** (p0012_01, p0012_02, p0012_03):
> Bak waves to Kim Sangshik, shouting that it has been a while. While shaking hands, Kim asks why he returned to hunting. Bak explains his wife is pregnant with their second son. Kim smiles, muttering that life is never easy.

### Beat 6

**GOLD** (p0010_04, p0011_01):
> The truck sends a hunter off with a wish of luck for the raid, while two more grab a quick meal before heading in.

**GEN** (p0013_01, p0013_02):
> Bak admits things only got tougher after his break. Kim Sangshik sips from his cup and warmly thanks Jin-Woo for arriving.

### Beat 7

**GOLD** (p0011_02, p0012_01, p0012_02, p0012_03):
> Song Chi-yul, a veteran of these raids, calls a greeting over his cup. Then an old friend appears — Bak, all smiles in his green puffer jacket. They shake hands, and Bak laughs that he only quit hunting because his wife is expecting their second son. Chi-yul admits that raiding for a fortune, like life itself, was never easy.

**GEN** (p0014_01, p0014_02, p0014_03):
> A friendly hunter welcomes Jin-Woo to the gate gathering point with a warm shoulder pat. He tells the youth that it is freezing outside and praises his dedication.

### Beat 8

**GOLD** (p0013_01, p0013_02, p0014_01):
> Bak just sighs at that. Then the group perks up — Jin-Woo has arrived, and they thank him for coming. A colleague claps his shoulder about the cold, and he tells them he'll pull his weight again today.

**GEN** (p0015_01, p0015_02):
> Bak points toward Jin-Woo's back while Kim Sangshik smiles. He explains the hunter arrived right after Bak quit, and his notorious nickname is...

### Beat 9

**GOLD** (p0014_02, p0014_03):
> The truck regulars ask if he's even eaten yet — everyone is glad to see him. Watching all this warmth, Bak asks the obvious question: is this guy some kind of powerful hunter?

**GEN** (p0016_01, p0016_02, p0016_03):
> As Jin-Woo walks further into the gathering area, he overhears Kim Sangshik and Bak gossiping behind his back. Kim chuckles and informs Bak that the young man is actually the 'World's Weakest' hunter who constantly gets injured even in low-rank dungeons, leaving him looking deeply dejected.

### Beat 10

**GOLD** (p0015_01, p0015_02, p0016_01, p0016_02, p0016_03):
> Another hunter sets him straight — Bak wouldn't know the nickname, since Jin-Woo joined right after he quit. Within earshot, the older hunters trade it like gossip: the weakest hunter in the guild. One asks if he's really the weakest; the other says he is, and that their dungeon must be a weak one since he was assigned to it. Then they hush each other, in case he can hear.

**GEN** (p0017_01, p0017_02):
> He mutters that he can hear those old geezers gossiping. He asks for coffee, but the vendor apologetically explains they just ran out.

### Beat 11

**GOLD** (p0017_01, p0017_02):
> He hears every word of it, and lets it pass. At the supply stand he asks for a cup of coffee, and the attendant apologizes — they've just run out.

**GEN** (p0018_02, p0018_03, p0018_04):
> He sighs, lamenting that even the coffee ran out before his arrival. He tells the guild vendor it is fine and turns to leave. Suddenly, a sharp voice screams his name, scolding him for being injured yet again.

### Beat 12

**GOLD** (p0018_02, p0018_03):
> Not even coffee today, he mutters — it feels like a bad sign. The attendant apologizes again, and he waves it off as nothing.

**GEN** (p0019_01, p0020_01, p0020_02):
> Lee Joo-hee, the party’s rookie healer, frantically scolds Jin-Woo for showing up with fresh facial bandages. He laughs nervously as they sit together on wooden pallets. She sighs, asking if his injuries actually required a hospital visit.

### Beat 13

**GOLD** (p0018_04, p0019_01, p0020_01):
> Lee Joo-hee, the party's healer, spots him across the lot and comes running — he's hurt again, she says, alarmed. He laughs it off, but she isn't buying it, and asks why his face keeps getting hurt.

**GEN** (p0020_03, p0021_01, p0021_02):
> Jin-Woo admits he was the only hunter injured during his last raid. He explains the high-ranked party skipped bringing a healer because they felt safe. Lee Joo-hee snaps, asking how they could abandon a healer just for their own safety.

### Beat 14

**GOLD** (p0020_02, p0020_03, p0021_01):
> They sit together on a stack of lumber while she asks if he actually saw a doctor this time. He admits he did. Joo-hee is stunned to learn he was the only one on his last team who got hurt at all.

**GEN** (p0022_01, p0022_02, p0022_03):
> Jin-Woo smiles weakly and tells Lee Joo-hee that he is simply used to getting hurt because of his weakness. She stares at him with a sympathetic gaze before they both look toward the entrance of the site.

### Beat 15

**GOLD** (p0021_02, p0022_01, p0022_02, p0022_03):
> The rest of his party outranked him badly enough that they skipped bringing a healer at all, he explains. Joo-hee asks why that would matter, if it's only their own safety they cared about. He shrugs it off with a tired smile. It's only because he's weak, he says, and he's used to it by now. She goes quiet, and the two of them head back toward the group.

**GEN** (p0022_04, p0023_01):
> Song Chi-yul calls the gathered hunters to order before the glowing Gate. He asks if they are comfortable with him leading the raid.

### Beat 16

**GOLD** (p0022_04, p0023_01, p0024_01, p0024_02):
> The full party gathers at the gate as Chi-yul modestly asks the group to let him lead the raid. The others back him without hesitation — he's the highest-ranked among them, one says, and worth trusting. Jin-Woo and Joo-hee greet him and ask him to look after the group.

**GEN** (p0024_01, p0024_02, p0024_03):
> Kim Sangshik crosses his arms with a confident smile. He says he has no objections because the proposed leader holds the highest rank. Bak nods warmly and agrees with the decision.

### Beat 17

**GOLD** (p0024_03, p0025_01, p0026_01, p0026_02, p0026_03, p0027_01):
> Chi-yul tells the group to head in, and they answer eager and ready. He promises to keep the injured Jin-Woo safely behind the front line, and Jin-Woo laughs along, no argument left in him. Kim Sang-shik scowls, uneasy, as they near the entrance. Someone calls Jin-Woo forward — okay, okay, he says — and he steps into the blinding blue light of the gate, and disappears.

**GEN** (p0025_01, p0026_01):
> The hunters rally at the entrance of the glowing blue Gate and prepare to enter the dungeon. Kim Sangshik tells Jin-Woo to stay safely behind the group. He simply nods and replies with a resigned smile.

### Beat 18

**GOLD** ():
> (no gold beat)

**GEN** (p0026_02, p0026_03, p0027_01):
> Lee Joo-hee tells Jin-Woo it is time to go. He agrees, taking a sharp breath and declaring that today is the day. The weakest hunter enters the portal to save his mother, yet whether he survives with fresh injuries remains uncertain.
