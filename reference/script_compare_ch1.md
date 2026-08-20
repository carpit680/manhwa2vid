# Script comparison — reference vs generated

Reference: `reference/ch1_gold_script.md` · Candidate: `projects/solo-leveling-ch1/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.43** of 237 salient reference terms
- order_tau: **0.38** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): barely, move, three, towering, glowing-eyed, guardians, close, weapons, brands, alive, refuses, believe, blade, present-day, commuter, nobody, twice, hunting, your, torn, open, inside, across, town, already

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 17 | 14 |
| words | 677 | 559 |
| avg_sentence_words | 15.0 | 13.6 |
| caption_markers_per_100w | 0.0 | 0.18 |
| speech_verbs_per_100w | 3.25 | 2.86 |
| connectives_per_100w | 3.69 | 2.86 |
| max_consecutive_pronoun_starts | 2 | 2 |
| pronoun_start_fraction | 0.2 | 0.29 |

## Side by side

### Beat 1

**reference** `p0002_01, p0003_01, p0004_01, p0005_01, p0006_01`

Sung Jin-Woo lies in a pool of his own blood, barely able to move. Three towering, glowing-eyed guardians close in on him, weapons raised. A voice brands him the weakest hunter alive. He refuses to believe it, even as the blade comes down again.

**candidate** `p0002_01, p0003_01, p0004_01`

Sung Jin-Woo lies bleeding on the ground as his breath catches in his throat. He tries to steady himself while sitting in a wide pool of his own blood. He tells himself that he is only a low-rank hunter for the Guild.

### Beat 2

**reference** `p0007_04`

Then the sky clears, over present-day Seoul.

**candidate** `p0005_01, p0006_01, p0007_01, p0007_04`

One massive stone sentinel raises its giant spear to deliver a final, crushing blow. He grits his teeth against the agony and curses his desperate fate. A blinding flash of light erupts as the vision shatters. A wide river flows through Seoul.

### Beat 3

**reference** `p0008_01, p0008_02`

Jin-Woo walks the morning streets with fresh bandages on his face, just another commuter nobody looks at twice.

**candidate** `p0008_01, p0008_02, p0009_01, p0009_02`

He walks through the bustling city streets while noting that his life stays on the line. He heads toward an active construction site where a glowing blue dungeon gate vibrates. Other pedestrians pass him by as he prepares for another dangerous day of work.

### Beat 4

**reference** `p0009_01, p0009_02`

Hunting is a job where your life is on the line, and today is a work day. A gate has torn open inside a construction site across town, and hunters are already gathering at the barriers.

**candidate** `p0010_01, p0010_03, p0010_04, p0011_01, p0011_02`

Kim Sangshik, the party's veteran supporting hunter, stops at a busy coffee stand for a morning drink. The vendor wishes him luck on his raid today while handing over the cup. Jin-Woo thinks about his sick mother's medical bills and the guild's meager pay.

### Beat 5

**reference** `p0010_01, p0010_03`

Inside the scaffolding, the gate hangs glowing blue. At the food truck below, Jin-Woo runs the same math as always — his mother's hospital bills against what the guild pays him.

**candidate** `p0012_01, p0012_02, p0012_03, p0013_01, p0013_02`

Bak, a supporting hunter, waves enthusiastically when he spots Kim Sangshik. Bak says it has been a while, prompting a surprised greeting from his old companion. As they shake hands, Kim asks why he returned after quitting the profession. Bak chuckles and replies that his wife is pregnant with their second son.

### Beat 6

**reference** `p0010_04, p0011_01`

The truck sends a hunter off with a wish of luck for the raid, while two more grab a quick meal before heading in.

**candidate** `p0014_01, p0014_02, p0014_03, p0015_01, p0015_02`

A friendly veteran hunter pats Jin-Woo on the shoulder and welcomes him to the site. He replies that he will be in their capable hands for the upcoming crawl. Kim Sangshik prepares to explain the young man's notorious nickname to a very curious Bak.

### Beat 7

**reference** `p0011_02, p0012_01, p0012_02, p0012_03`

Song Chi-yul, a veteran of these raids, calls a greeting over his cup. Then an old friend appears — Bak, all smiles in his green puffer jacket. They shake hands, and Bak laughs that he only quit hunting because his wife is expecting their second son. Chi-yul admits that raiding for a fortune, like life itself, was never easy.

**candidate** `p0016_01, p0016_02, p0016_03`

Kim Sangshik explains that Bak is looking at the world’s weakest hunter. Even in low-rank dungeons, the young man manages to get himself severely hospitalized. Jin-Woo stands nearby and feels deeply dejected after overhearing their cruel, public gossip.

### Beat 8

**reference** `p0013_01, p0013_02, p0014_01`

Bak just sighs at that. Then the group perks up — Jin-Woo has arrived, and they thank him for coming. A colleague claps his shoulder about the cold, and he tells them he'll pull his weight again today.

**candidate** `p0017_01`

He mutters to himself about the old geezers who cannot stop talking about him.

### Beat 9

**reference** `p0014_02, p0014_03`

The truck regulars ask if he's even eaten yet — everyone is glad to see him. Watching all this warmth, Bak asks the obvious question: is this guy some kind of powerful hunter?

**candidate** `p0017_02, p0018_02, p0018_03, p0018_04, p0019_01`

A coffee vendor apologizes because the stand just ran out of coffee. Jin-Woo sighs at his luck until Lee Joo-hee, the party's supporting healer, shouts his name. She immediately scolds him for the fresh bandages and the injuries on his face.

### Beat 10

**reference** `p0015_01, p0015_02, p0016_01, p0016_02, p0016_03`

Another hunter sets him straight — Bak wouldn't know the nickname, since Jin-Woo joined right after he quit. Within earshot, the older hunters trade it like gossip: the weakest hunter in the guild. One asks if he's really the weakest; the other says he is, and that their dungeon must be a weak one since he was assigned to it. Then they hush each other, in case he can hear.

**candidate** `p0020_01, p0020_02, p0020_03, p0021_01`

Sitting on wooden pallets, Jin-Woo admits he was recently hospitalized after a previous raid. He tells a shocked Lee Joo-hee that the higher-ranked hunters decided to skip bringing a healer. His injuries were the only ones sustained because he was the only weak link present.

### Beat 11

**reference** `p0017_01, p0017_02`

He hears every word of it, and lets it pass. At the supply stand he asks for a cup of coffee, and the attendant apologizes — they've just run out.

**candidate** `p0021_02, p0022_01, p0022_02, p0022_03, p0022_04`

Lee Joo-hee snaps at the reckless decision to enter a dungeon without proper medical support. Jin-Woo merely smiles weakly and says he is quite used to being the one hurt. They both turn their attention to the group gathering around the vibrating blue gate.

### Beat 12

**reference** `p0018_02, p0018_03`

Not even coffee today, he mutters — it feels like a bad sign. The attendant apologizes again, and he waves it off as nothing.

**candidate** `p0023_01, p0024_01, p0024_02`

Song Chi-yul, the party's veteran leader, asks the gathered hunters if they will let him lead. Kim Sangshik agrees since the older man is the highest-ranked hunter present. Bak and the others nod because they trust the skills of the veteran.

### Beat 13

**reference** `p0018_04, p0019_01, p0020_01`

Lee Joo-hee, the party's healer, spots him across the lot and comes running — he's hurt again, she says, alarmed. He laughs it off, but she isn't buying it, and asks why his face keeps getting hurt.

**candidate** `p0024_03, p0025_01`

Jin-Woo smiles modestly beside Lee Joo-hee. He asks their leader to look after them as they prepare to head out.

### Beat 14

**reference** `p0020_02, p0020_03, p0021_01`

They sit together on a stack of lumber while she asks if he actually saw a doctor this time. He admits he did. Joo-hee is stunned to learn he was the only one on his last team who got hurt at all.

**candidate** `p0026_01, p0026_02, p0026_03, p0027_01`

Kim Sangshik tells the young man to stay safely behind the others to avoid further injury. Jin-Woo takes a deep breath as he and Lee Joo-hee step into the swirling energy. Whether he will successfully clear the upcoming dungeon raid without sustaining serious injuries remains to be seen.

### Beat 15

**reference** `p0021_02, p0022_01, p0022_02, p0022_03`

The rest of his party outranked him badly enough that they skipped bringing a healer at all, he explains. Joo-hee asks why that would matter, if it's only their own safety they cared about. He shrugs it off with a tired smile. It's only because he's weak, he says, and he's used to it by now. She goes quiet, and the two of them head back toward the group.

**candidate** 

(no candidate beat)

### Beat 16

**reference** `p0022_04, p0023_01, p0024_01, p0024_02`

The full party gathers at the gate as Chi-yul modestly asks the group to let him lead the raid. The others back him without hesitation — he's the highest-ranked among them, one says, and worth trusting. Jin-Woo and Joo-hee greet him and ask him to look after the group.

**candidate** 

(no candidate beat)

### Beat 17

**reference** `p0024_03, p0025_01, p0026_01, p0026_02, p0026_03, p0027_01`

Chi-yul tells the group to head in, and they answer eager and ready. He promises to keep the injured Jin-Woo safely behind the front line, and Jin-Woo laughs along, no argument left in him. Kim Sang-shik scowls, uneasy, as they near the entrance. Someone calls Jin-Woo forward — okay, okay, he says — and he steps into the blinding blue light of the gate, and disappears.

**candidate** 

(no candidate beat)
