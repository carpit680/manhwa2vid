# Script comparison — gold (hand-written) vs generated

Gold: `reference/ch1_gold_script.md` · Candidate: `projects/solo-leveling-ch1/script.json`

## Metrics (the target is the GOLD column, not 'better than last run')

| metric | gold | candidate |
|---|---|---|
| beats | 17 | 18 |
| words | 677 | 689 |
| avg_sentence_words | 15.0 | 14.1 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 3.25 | 3.63 |
| connectives_per_100w | 3.69 | 3.48 |
| max_consecutive_pronoun_starts | 2 | 2 |
| pronoun_start_fraction | 0.2 | 0.31 |

## Side by side

### Beat 1

**GOLD** (p0002_01, p0003_01, p0004_01, p0005_01, p0006_01):
> Sung Jin-Woo lies in a pool of his own blood, barely able to move. Three towering, glowing-eyed guardians close in on him, weapons raised. A voice brands him the weakest hunter alive. He refuses to believe it, even as the blade comes down again.

**GEN** (p0002_01, p0003_01, p0004_01):
> Sung Jin-Woo lies bleeding on the hard ground, gasping heavily as his strength slips away. He calls himself an E-rank hunter, the absolute weakest member of the guild. But now he sits helplessly in a wide, spreading pool of his own blood.

### Beat 2

**GOLD** (p0007_04):
> Then the sky clears, over present-day Seoul.

**GEN** (p0005_01, p0006_01, p0007_01, p0007_04):
> A massive stone sentinel raises its weapon while he watches through a bloodshot eye. He curses his helplessness as the killing blow descends. A blinding flash of light consumes the chamber. Then the sky clears, over present-day Seoul.

### Beat 3

**GOLD** (p0008_01, p0008_02):
> Jin-Woo walks the morning streets with fresh bandages on his face, just another commuter nobody looks at twice.

**GEN** (p0008_01, p0008_02, p0009_01, p0009_02):
> Walking the morning streets with fresh bandages, he is just another commuter nobody notices. He thinks about how hunting is a job where your life is always on the line. He eventually reaches a construction site where a glowing blue gate is locked behind scaffolding.

### Beat 4

**GOLD** (p0009_01, p0009_02):
> Hunting is a job where your life is on the line, and today is a work day. A gate has torn open inside a construction site across town, and hunters are already gathering at the barriers.

**GEN** (p0010_01, p0010_03, p0010_04):
> Near the glowing blue portal, Kim Sangshik, an experienced hunter who catches up with other members, leans against a food truck. Jin-Woo's thoughts reveal that he is motivated to hunt in order to pay his mother's medical bills as a vendor serves coffee.

### Beat 5

**GOLD** (p0010_01, p0010_03):
> Inside the scaffolding, the gate hangs glowing blue. At the food truck below, Jin-Woo runs the same math as always — his mother's hospital bills against what the guild pays him.

**GEN** (p0011_01, p0011_02):
> Kim Sangshik takes a cup of coffee from the vendor. He takes a quick sip, but a loud shout calling his name interrupts him. He pauses in surprise, looking toward the origin of the sudden call.

### Beat 6

**GOLD** (p0010_04, p0011_01):
> The truck sends a hunter off with a wish of luck for the raid, while two more grab a quick meal before heading in.

**GEN** (p0012_01, p0012_02, p0012_03):
> Bak waves enthusiastically, greeting Kim Sangshik for the first time in ages. Kim asks why he returned after quitting, but Bak admits his wife is expecting another son. He needs a raid fortune, and Kim muses that life is never easy.

### Beat 7

**GOLD** (p0011_02, p0012_01, p0012_02, p0012_03):
> Song Chi-yul, a veteran of these raids, calls a greeting over his cup. Then an old friend appears — Bak, all smiles in his green puffer jacket. They shake hands, and Bak laughs that he only quit hunting because his wife is expecting their second son. Chi-yul admits that raiding for a fortune, like life itself, was never easy.

**GEN** (p0013_01, p0013_02):
> Bak admits that things only worsened during his break. Kim Sangshik sips his coffee and tells Jin-Woo he is glad he arrived.

### Beat 8

**GOLD** (p0013_01, p0013_02, p0014_01):
> Bak just sighs at that. Then the group perks up — Jin-Woo has arrived, and they thank him for coming. A colleague claps his shoulder about the cold, and he tells them he'll pull his weight again today.

**GEN** (p0014_01, p0014_02, p0014_03):
> A veteran hunter in a green jacket pats his shoulder and says it is freezing outside. He replies that he will be in the hunter's hands today as well.

### Beat 9

**GOLD** (p0014_02, p0014_03):
> The truck regulars ask if he's even eaten yet — everyone is glad to see him. Watching all this warmth, Bak asks the obvious question: is this guy some kind of powerful hunter?

**GEN** (p0015_01, p0015_02):
> Bak gives a thumbs up as Jin-Woo walks away. Kim Sangshik explains that since he joined after Bak quit, the hunter’s nickname is...

### Beat 10

**GOLD** (p0015_01, p0015_02, p0016_01, p0016_02, p0016_03):
> Another hunter sets him straight — Bak wouldn't know the nickname, since Jin-Woo joined right after he quit. Within earshot, the older hunters trade it like gossip: the weakest hunter in the guild. One asks if he's really the weakest; the other says he is, and that their dungeon must be a weak one since he was assigned to it. Then they hush each other, in case he can hear.

**GEN** (p0016_01, p0016_02, p0016_03):
> As he walks further into the site, he overhears the gossip behind his back. The two older hunters discuss how he is the World's Weakest, explaining that his presence means the E-rank dungeon will be exceptionally easy.

### Beat 11

**GOLD** (p0017_01, p0017_02):
> He hears every word of it, and lets it pass. At the supply stand he asks for a cup of coffee, and the attendant apologizes — they've just run out.

**GEN** (p0017_01, p0017_02):
> He sighs that he hears the older men gossiping behind his back. He asks for coffee, but the vendor apologizes that they just ran out.

### Beat 12

**GOLD** (p0018_02, p0018_03):
> Not even coffee today, he mutters — it feels like a bad sign. The attendant apologizes again, and he waves it off as nothing.

**GEN** (p0018_02, p0018_03, p0018_04):
> He mutters that missing out on coffee feels terrible, even as he tells the vendor it is fine and leaves. Just then, an angry voice snaps that he is already injured again.

### Beat 13

**GOLD** (p0018_04, p0019_01, p0020_01):
> Lee Joo-hee, the party's healer, spots him across the lot and comes running — he's hurt again, she says, alarmed. He laughs it off, but she isn't buying it, and asks why his face keeps getting hurt.

**GEN** (p0019_01, p0020_01, p0020_02):
> Lee Joo-hee, the party's rookie healer, snaps at Jin-Woo for arriving with fresh facial wounds. He laughs nervously as they sit on wooden pallets. She asks if he even visited a hospital, which he simply admits.

### Beat 14

**GOLD** (p0020_02, p0020_03, p0021_01):
> They sit together on a stack of lumber while she asks if he actually saw a doctor this time. He admits he did. Joo-hee is stunned to learn he was the only one on his last team who got hurt at all.

**GEN** (p0020_03, p0021_01, p0021_02):
> Jin-Woo admits he was the only one injured during his last raid. Since the others were high-ranked, they neglected to bring a healer for support. Lee Joo-hee asks if they really skipped safety measures just because they felt invincible.

### Beat 15

**GOLD** (p0021_02, p0022_01, p0022_02, p0022_03):
> The rest of his party outranked him badly enough that they skipped bringing a healer at all, he explains. Joo-hee asks why that would matter, if it's only their own safety they cared about. He shrugs it off with a tired smile. It's only because he's weak, he says, and he's used to it by now. She goes quiet, and the two of them head back toward the group.

**GEN** (p0022_01, p0022_02, p0022_03):
> Jin-Woo smiles weakly and tells Lee Joo-hee that he is used to his weakness. She looks back at him with a sad and sympathetic gaze. But they soon turn their attention toward the construction site entrance as he murmurs and she quietly agrees.

### Beat 16

**GOLD** (p0022_04, p0023_01, p0024_01, p0024_02):
> The full party gathers at the gate as Chi-yul modestly asks the group to let him lead the raid. The others back him without hesitation — he's the highest-ranked among them, one says, and worth trusting. Jin-Woo and Joo-hee greet him and ask him to look after the group.

**GEN** (p0022_04, p0023_01):
> The raid group gathers before the glowing blue portal. Song Chi-yul, an experienced hunter chosen by the raid group to act as their party leader, steps forward and asks if everyone is comfortable with him leading the raid.

### Beat 17

**GOLD** (p0024_03, p0025_01, p0026_01, p0026_02, p0026_03, p0027_01):
> Chi-yul tells the group to head in, and they answer eager and ready. He promises to keep the injured Jin-Woo safely behind the front line, and Jin-Woo laughs along, no argument left in him. Kim Sang-shik scowls, uneasy, as they near the entrance. Someone calls Jin-Woo forward — okay, okay, he says — and he steps into the blinding blue light of the gate, and disappears.

**GEN** (p0024_01, p0024_02, p0024_03, p0025_01):
> Kim Sangshik gladly accepts the leadership choice since the veteran holds the highest rank. But Bak also agrees and says he trusts the leader's skills. A few more hunters quickly join the consensus and voice their support as well. Jin-Woo smiles alongside Lee Joo-hee and asks the leader to look after them. With the decision finalized, the entire raid party eagerly marches together into the glowing blue portal.

### Beat 18

**GOLD** ():
> (no gold beat)

**GEN** (p0026_01, p0026_02, p0026_03, p0027_01):
> Kim Sangshik tells Jin-Woo to stay safely behind them because of his injuries. He replies with a resigned laugh even as Lee Joo-hee urges him to follow her inside. After taking a sharp, determined breath, he steps into the light, unsure if the party will survive the dangerous environment of the dungeon.
