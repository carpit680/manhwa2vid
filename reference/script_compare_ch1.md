# Script comparison — gold (hand-written) vs generated

Gold: `reference/ch1_gold_script.md` · Candidate: `projects/solo-leveling-ch1/script.json`

## Metrics (the target is the GOLD column, not 'better than last run')

| metric | gold | candidate |
|---|---|---|
| beats | 17 | 18 |
| words | 677 | 718 |
| avg_sentence_words | 15.0 | 14.4 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 3.25 | 2.79 |
| connectives_per_100w | 3.69 | 4.6 |
| max_consecutive_pronoun_starts | 2 | 2 |
| pronoun_start_fraction | 0.2 | 0.28 |

## Side by side

### Beat 1

**GOLD** (p0002_01, p0003_01, p0004_01, p0005_01, p0006_01):
> Sung Jin-Woo lies in a pool of his own blood, barely able to move. Three towering, glowing-eyed guardians close in on him, weapons raised. A voice brands him the weakest hunter alive. He refuses to believe it, even as the blade comes down again.

**GEN** (p0002_01, p0003_01, p0004_01):
> Sung Jin-Woo, the world’s weakest hunter, lies shattered in a pool of blood. He admits that as an E-Rank, the lowest hunter classification, he never expected this. Stone sentinels loom over him—but this nightmare starts hours earlier.

### Beat 2

**GOLD** (p0007_04):
> Then the sky clears, over present-day Seoul.

**GEN** (p0005_01, p0006_01, p0007_01, p0007_04):
> He gasps for breath while his vision blurs with his own blood. Above him, a massive stone sentinel with glowing blue eyes raises a heavy spear. Then the giant weapon swings down in a swift flash, unleashing a spray of crimson. He curses his helpless situation in the final moments before the lethal blow lands. But the path to this nightmare for him begins hours earlier over a quiet Seoul.

### Beat 3

**GOLD** (p0008_01, p0008_02):
> Jin-Woo walks the morning streets with fresh bandages on his face, just another commuter nobody looks at twice.

**GEN** (p0008_01, p0008_02, p0009_01, p0009_02):
> That is where this day is headed, but it starts hours earlier on a Seoul street. He walks among commuters pausing to gaze at a shop window. He admits that hunting is a job where his life stays on the line. A gate, a magical gateway to another world, pulses inside construction scaffolding.

### Beat 4

**GOLD** (p0009_01, p0009_02):
> Hunting is a job where your life is on the line, and today is a work day. A gate has torn open inside a construction site across town, and hunters are already gathering at the barriers.

**GEN** (p0010_01, p0010_03, p0010_04, p0011_01, p0011_02):
> A glowing blue portal vibrates within metal scaffolding amidst swirling white mist. Nearby, Kim Sangshik, a friendly veteran hunter, leans against a food truck, reflecting on how Jin-Woo risks his life in raids to pay for his mother's medical bills. After receiving a warm beverage from a guild clerk, Kim Sangshik sits at a table with Song Chi-yul, a veteran raid party leader, before turning in surprise as his name is called.

### Beat 5

**GOLD** (p0010_01, p0010_03):
> Inside the scaffolding, the gate hangs glowing blue. At the food truck below, Jin-Woo runs the same math as always — his mother's hospital bills against what the guild pays him.

**GEN** (p0012_01, p0012_02, p0012_03):
> Bak, a burly returning hunter, waves and tells Kim Sangshik it has been a long time. Kim asks why he returned, and Bak admits his wife is pregnant. The veteran sighs that life is never easy when raiding for fortune.

### Beat 6

**GOLD** (p0010_04, p0011_01):
> The truck sends a hunter off with a wish of luck for the raid, while two more grab a quick meal before heading in.

**GEN** (p0013_01, p0013_02):
> Bak sighs that things have only worsened since his break. Kim Sangshik waves while welcoming Jin-Woo to the raid.

### Beat 7

**GOLD** (p0011_02, p0012_01, p0012_02, p0012_03):
> Song Chi-yul, a veteran of these raids, calls a greeting over his cup. Then an old friend appears — Bak, all smiles in his green puffer jacket. They shake hands, and Bak laughs that he only quit hunting because his wife is expecting their second son. Chi-yul admits that raiding for a fortune, like life itself, was never easy.

**GEN** (p0014_01, p0014_02, p0014_03):
> Jin-Woo thanks a fellow hunter for the warm greeting on this cold morning. Kim Sangshik waves enthusiastically, leading Bak to wonder if this popular young man is actually a powerful hunter everyone is happy to see.

### Beat 8

**GOLD** (p0013_01, p0013_02, p0014_01):
> Bak just sighs at that. Then the group perks up — Jin-Woo has arrived, and they thank him for coming. A colleague claps his shoulder about the cold, and he tells them he'll pull his weight again today.

**GEN** (p0015_01, p0015_02):
> Bak watches as the young man walks away into the construction site. Kim Sangshik smiles knowingly and prepares to reveal the boy's notorious nickname.

### Beat 9

**GOLD** (p0014_02, p0014_03):
> The truck regulars ask if he's even eaten yet — everyone is glad to see him. Watching all this warmth, Bak asks the obvious question: is this guy some kind of powerful hunter?

**GEN** (p0016_01, p0016_02, p0016_03):
> He ignores the gossip while walking past heavy excavators. The veterans laugh that he is the world's weakest hunter even in E-rank dungeons. He looks downcast, hearing them joke that the raid will be easy because he is there.

### Beat 10

**GOLD** (p0015_01, p0015_02, p0016_01, p0016_02, p0016_03):
> Another hunter sets him straight — Bak wouldn't know the nickname, since Jin-Woo joined right after he quit. Within earshot, the older hunters trade it like gossip: the weakest hunter in the guild. One asks if he's really the weakest; the other says he is, and that their dungeon must be a weak one since he was assigned to it. Then they hush each other, in case he can hear.

**GEN** (p0017_01, p0017_02):
> Jin-Woo sighs at the old geezers' loud gossip. He asks a guild clerk for coffee, but the man replies that they have already run out.

### Beat 11

**GOLD** (p0017_01, p0017_02):
> He hears every word of it, and lets it pass. At the supply stand he asks for a cup of coffee, and the attendant apologizes — they've just run out.

**GEN** (p0018_02, p0018_03, p0018_04):
> He mutters that lacking coffee feels miserable while turning from the booth. The guild clerk tries to address him, but he insists it is fine and walks off. A sudden shout startles him by yelling that he is injured again.

### Beat 12

**GOLD** (p0018_02, p0018_03):
> Not even coffee today, he mutters — it feels like a bad sign. The attendant apologizes again, and he waves it off as nothing.

**GEN** (p0019_01, p0020_01, p0020_02):
> Lee Joo-hee, the party’s caring healer, shouts at Jin-Woo while demanding to know why his face is injured again. They sit on wooden pallets where she asks if he visited a hospital, and he admits he had to.

### Beat 13

**GOLD** (p0018_04, p0019_01, p0020_01):
> Lee Joo-hee, the party's healer, spots him across the lot and comes running — he's hurt again, she says, alarmed. He laughs it off, but she isn't buying it, and asks why his face keeps getting hurt.

**GEN** (p0020_03, p0021_01, p0021_02):
> Jin-Woo admits he was the only one wounded during his last raid, prompting Lee Joo-hee to ask how that happened. He explains the high-ranked members felt safe enough to skip a healer, but she asks if they truly ignored safety just because they felt secure.

### Beat 14

**GOLD** (p0020_02, p0020_03, p0021_01):
> They sit together on a stack of lumber while she asks if he actually saw a doctor this time. He admits he did. Joo-hee is stunned to learn he was the only one on his last team who got hurt at all.

**GEN** (p0022_01, p0022_02, p0022_03):
> Jin-Woo gives a resigned smile while admitting he is simply used to getting hurt because of his weakness. Lee Joo-hee watches him with a sorrowful silence until he finally stands to join the rest of the raid.

### Beat 15

**GOLD** (p0021_02, p0022_01, p0022_02, p0022_03):
> The rest of his party outranked him badly enough that they skipped bringing a healer at all, he explains. Joo-hee asks why that would matter, if it's only their own safety they cared about. He shrugs it off with a tired smile. It's only because he's weak, he says, and he's used to it by now. She goes quiet, and the two of them head back toward the group.

**GEN** (p0022_04, p0023_01):
> Gathering before the glowing portal, Jin-Woo joins the other hunters. Song Chi-yul asks the group to let him act as their raid leader.

### Beat 16

**GOLD** (p0022_04, p0023_01, p0024_01, p0024_02):
> The full party gathers at the gate as Chi-yul modestly asks the group to let him lead the raid. The others back him without hesitation — he's the highest-ranked among them, one says, and worth trusting. Jin-Woo and Joo-hee greet him and ask him to look after the group.

**GEN** (p0024_01, p0024_02, p0024_03):
> Kim Sangshik crosses his arms and smiles in the freezing air. Bak grins and says they can easily trust the raid leader's skills. A hunter in a blue jacket and another in a green jacket quickly volunteer to join. Jin-Woo stands beside Lee Joo-hee and smiles warmly. He cheerfully asks the off-screen leader to look after them during the dungeon exploration.

### Beat 17

**GOLD** (p0024_03, p0025_01, p0026_01, p0026_02, p0026_03, p0027_01):
> Chi-yul tells the group to head in, and they answer eager and ready. He promises to keep the injured Jin-Woo safely behind the front line, and Jin-Woo laughs along, no argument left in him. Kim Sang-shik scowls, uneasy, as they near the entrance. Someone calls Jin-Woo forward — okay, okay, he says — and he steps into the blinding blue light of the gate, and disappears.

**GEN** (p0025_01, p0026_01, p0026_02):
> Hunters shout for everyone to enter the dungeon as the raid begins. Kim Sangshik tells Jin-Woo to stay safely behind them because of his injuries. He agrees before Lee Joo-hee calls for him to follow her into the gate.

### Beat 18

**GOLD** ():
> (no gold beat)

**GEN** (p0026_03, p0027_01):
> Defying his deadly premonition, he exhales and enters the gate. He must survive the dungeon raid without sustaining serious injuries.
