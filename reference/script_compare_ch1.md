# Script comparison — reference vs generated

Reference: `reference/ch1_gold_script.md` · Candidate: `projects/solo-leveling-ch1/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.45** of 237 salient reference terms
- order_tau: **0.41** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): barely, move, three, towering, glowing-eyed, guardians, close, weapons, brands, alive, refuses, believe, blade, clears, present-day, morning, streets, fresh, bandages, commuter, hunting, your, work, torn, open

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 17 | 14 |
| words | 677 | 623 |
| avg_sentence_words | 15.0 | 13.5 |
| caption_markers_per_100w | 0.0 | 0.16 |
| speech_verbs_per_100w | 3.25 | 3.53 |
| connectives_per_100w | 3.69 | 2.41 |
| max_consecutive_pronoun_starts | 2 | 2 |
| pronoun_start_fraction | 0.2 | 0.33 |

## Side by side

### Beat 1

**reference** `p0002_01, p0003_01, p0004_01, p0005_01, p0006_01`

Sung Jin-Woo lies in a pool of his own blood, barely able to move. Three towering, glowing-eyed guardians close in on him, weapons raised. A voice brands him the weakest hunter alive. He refuses to believe it, even as the blade comes down again.

**candidate** `p0002_01, p0003_01, p0004_01`

Sung Jin-Woo, an E-Rank hunter, lies on the ground and gasps for breath while bleeding heavily. He says that he is only an E-rank hunter for the Hunter Guild. Blood pools around him as he sits upright and continues to struggle.

### Beat 2

**reference** `p0007_04`

Then the sky clears, over present-day Seoul.

**candidate** `p0005_01, p0006_01, p0007_01, p0007_04`

He gasps for breath as the massive stone sentinel, a minor antagonist, looms with a raised spear. Gritting his teeth in agony, he curses his helplessness as the enemy strikes. A sudden blinding flash of light consumes the chamber to end the nightmare. Far away, bridges stretch across a wide river under the distant city skyline.

### Beat 3

**reference** `p0008_01, p0008_02`

Jin-Woo walks the morning streets with fresh bandages on his face, just another commuter nobody looks at twice.

**candidate** `p0008_01, p0008_02, p0009_01, p0009_02`

He navigates the crowded crosswalk, just another face that nobody looks at twice. He thinks that his career is a trade where his life is always on the line. Arriving at a Seoul construction site, he finds the shimmering Gate, a portal into a monster-filled dungeon.

### Beat 4

**reference** `p0009_01, p0009_02`

Hunting is a job where your life is on the line, and today is a work day. A gate has torn open inside a construction site across town, and hunters are already gathering at the barriers.

**candidate** `p0010_01, p0010_03, p0010_04, p0011_01, p0011_02`

The gate hums behind the scaffolding, a glowing portal to another dimension. Kim Sangshik, a supporting hunter waits by a food truck while Jin-Woo worries about paying his mother’s medical bills. The vendor wishes Kim luck on the raid and hands over a coffee. Kim offers his thanks before a friend suddenly calls his name.

### Beat 5

**reference** `p0010_01, p0010_03`

Inside the scaffolding, the gate hangs glowing blue. At the food truck below, Jin-Woo runs the same math as always — his mother's hospital bills against what the guild pays him.

**candidate** `p0012_01, p0012_02, p0012_03, p0013_01, p0013_02`

Bak waves enthusiastically to greet Kim Sangshik. Bak says it has been a long time since they last saw each other. Kim asks why he returned to this dangerous field. He replies that his wife is currently pregnant with their second son.

### Beat 6

**reference** `p0010_04, p0011_01`

The truck sends a hunter off with a wish of luck for the raid, while two more grab a quick meal before heading in.

**candidate** `p0014_01, p0014_02, p0014_03, p0015_01, p0015_02`

A veteran hunter welcomes Jin-Woo to the gate and remarks on the freezing weather. He laughs the praise away, admitting he needs their protection once again. Kim Sangshik asks if he has eaten, prompting Bak to wonder if he is a powerful hunter. Kim smiles and tells Bak that his secret nickname is...

### Beat 7

**reference** `p0011_02, p0012_01, p0012_02, p0012_03`

Song Chi-yul, a veteran of these raids, calls a greeting over his cup. Then an old friend appears — Bak, all smiles in his green puffer jacket. They shake hands, and Bak laughs that he only quit hunting because his wife is expecting their second son. Chi-yul admits that raiding for a fortune, like life itself, was never easy.

**candidate** `p0016_01, p0016_02, p0016_03, p0017_01, p0017_02`

Jin-Woo walks toward the gate while Bak asks if he is truly the weakest. Kim Sangshik remarks that the dungeon will be easy since the bottom-ranked hunter joined. He mutters that he can hear the old men mocking him. When he asks for coffee, the coffee vendor apologizes because the stand just ran out.

### Beat 8

**reference** `p0013_01, p0013_02, p0014_01`

Bak just sighs at that. Then the group perks up — Jin-Woo has arrived, and they thank him for coming. A colleague claps his shoulder about the cold, and he tells them he'll pull his weight again today.

**candidate** `p0018_02, p0018_03, p0018_04`

He sighs heavily because missing out on coffee feels like a defeat. He walks away when the coffee vendor tries to address him, quietly telling him that it is fine. Then, a sudden, loud shout accusing him of being injured again startles him and makes him jump.

### Beat 9

**reference** `p0014_02, p0014_03`

The truck regulars ask if he's even eaten yet — everyone is glad to see him. Watching all this warmth, Bak asks the obvious question: is this guy some kind of powerful hunter?

**candidate** `p0019_01`

Lee Joo-hee, the supporting healer, frantically asks Jin-Woo why his face is hurt again.

### Beat 10

**reference** `p0015_01, p0015_02, p0016_01, p0016_02, p0016_03`

Another hunter sets him straight — Bak wouldn't know the nickname, since Jin-Woo joined right after he quit. Within earshot, the older hunters trade it like gossip: the weakest hunter in the guild. One asks if he's really the weakest; the other says he is, and that their dungeon must be a weak one since he was assigned to it. Then they hush each other, in case he can hear.

**candidate** `p0020_01, p0020_02, p0020_03, p0021_01, p0021_02`

Jin-Woo sits on a stack of wooden pallets next to Lee Joo-hee. She asks with surprise if he actually ended up in the hospital after his last raid. He laughs sheepishly and admits that he spent some time recovering there.

### Beat 11

**reference** `p0017_01, p0017_02`

He hears every word of it, and lets it pass. At the supply stand he asks for a cup of coffee, and the attendant apologizes — they've just run out.

**candidate** `p0022_01, p0022_02, p0022_03, p0022_04, p0023_01`

Jin-Woo smiles weakly and tells Lee Joo-hee that he is simply used to being the weakest. The pair watches the crowd gather near the glowing blue Gate as a voice calls for order. Song Chi-yul, the raid's veteran leader steps forward and asks if everyone consents to him leading the mission.

### Beat 12

**reference** `p0018_02, p0018_03`

Not even coffee today, he mutters — it feels like a bad sign. The attendant apologizes again, and he waves it off as nothing.

**candidate** `p0024_01, p0024_02, p0024_03`

Kim Sangshik crosses his arms and says he has no complaints about their highest-ranked nominee. Bak says they can easily trust the veteran because of his reliable skills. Another veteran hunter stands nearby in silent agreement with the choice.

### Beat 13

**reference** `p0018_04, p0019_01, p0020_01`

Lee Joo-hee, the party's healer, spots him across the lot and comes running — he's hurt again, she says, alarmed. He laughs it off, but she isn't buying it, and asks why his face keeps getting hurt.

**candidate** `p0025_01, p0026_01, p0026_02`

Kim Sangshik tells Jin-Woo to stay behind the others due to his injuries. He offers a resigned smile and accepts the advice with a soft laugh. Then, Lee Joo-hee tells him that they should head inside. He agrees, and they step together into the swirling blue energy of the dungeon gate.

### Beat 14

**reference** `p0020_02, p0020_03, p0021_01`

They sit together on a stack of lumber while she asks if he actually saw a doctor this time. He admits he did. Joo-hee is stunned to learn he was the only one on his last team who got hurt at all.

**candidate** `p0026_03, p0027_01`

He takes a sharp breath and steels his resolve to conquer the dungeon. He tells himself that today is his moment. A brilliant blue light completely engulfs him as he steps through the gateway.

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
