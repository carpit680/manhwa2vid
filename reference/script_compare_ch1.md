# Script comparison — reference vs generated

Reference: `reference/ch1_gold_script.md` · Candidate: `projects/solo-leveling-ch1/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.45** of 237 salient reference terms
- order_tau: **0.26** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): barely, able, three, towering, glowing-eyed, guardians, close, brands, alive, refuses, believe, blade, present-day, streets, fresh, bandages, commuter, nobody, twice, your, work, torn, open, inside, across

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 17 | 14 |
| words | 677 | 588 |
| avg_sentence_words | 15.0 | 14.0 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 3.25 | 2.89 |
| connectives_per_100w | 3.69 | 2.55 |
| max_consecutive_pronoun_starts | 2 | 2 |
| pronoun_start_fraction | 0.2 | 0.33 |

## Side by side

### Beat 1

**reference** `p0002_01, p0003_01, p0004_01, p0005_01, p0006_01`

Sung Jin-Woo lies in a pool of his own blood, barely able to move. Three towering, glowing-eyed guardians close in on him, weapons raised. A voice brands him the weakest hunter alive. He refuses to believe it, even as the blade comes down again.

**candidate** `p0002_01, p0003_01, p0004_01`

Sung Jin-Woo, an E-Rank hunter, lies bleeding on the cold floor. He clutches his injured hand and struggles to breathe as blood pools around his legs. He gasps heavily, saying that he is merely a weak, low-ranking member of the Hunter Guild.

### Beat 2

**reference** `p0007_04`

Then the sky clears, over present-day Seoul.

**candidate** `p0005_01, p0006_01, p0007_01, p0007_04`

A giant statue raises its spear as he grits his teeth against the pain. He curses his fate while the weapon descends in a blinding flash of light. The city of Seoul stands peaceful along the wide river under a clear morning sky.

### Beat 3

**reference** `p0008_01, p0008_02`

Jin-Woo walks the morning streets with fresh bandages on his face, just another commuter nobody looks at twice.

**candidate** `p0008_01, p0008_02, p0009_01, p0009_02`

He walks through a crowded city crosswalk with his hood up and eyes down. He thinks about the dangerous trade where his life is constantly on the line. The journey leads him toward a D-rank Gate contained within scaffolding at a local construction site.

### Beat 4

**reference** `p0009_01, p0009_02`

Hunting is a job where your life is on the line, and today is a work day. A gate has torn open inside a construction site across town, and hunters are already gathering at the barriers.

**candidate** `p0010_01, p0010_03, p0010_04, p0011_01, p0011_02`

The magical gate vibrates with energy as the raid party prepares to enter. Jin-Woo, an E-rank hunter, desperately needs the guild money for his mother's medical bills. Nearby, Kim Sangshik, a supporting hunter, waits by a food truck for the raid to begin. The coffee vendor hands Kim a hot drink and wishes him luck on his mission.

### Beat 5

**reference** `p0010_01, p0010_03`

Inside the scaffolding, the gate hangs glowing blue. At the food truck below, Jin-Woo runs the same math as always — his mother's hospital bills against what the guild pays him.

**candidate** `p0012_01, p0012_02, p0012_03, p0013_01, p0013_02`

Bak, a former hunter, waves to Kim Sangshik and says it has been a while. They shake hands as Kim asks why he returned to this dangerous job. Bak replies that his wife is pregnant with their second son and he needs the money.

### Beat 6

**reference** `p0010_04, p0011_01`

The truck sends a hunter off with a wish of luck for the raid, while two more grab a quick meal before heading in.

**candidate** `p0014_01, p0014_02, p0014_03, p0015_01, p0015_02`

A hunter pats the newcomer on the shoulder and welcomes him. Kim Sangshik asks if he has eaten while Bak observes the warm greeting from the group. He wonders if this newcomer is a powerful hunter because everyone seems happy to see him.

### Beat 7

**reference** `p0011_02, p0012_01, p0012_02, p0012_03`

Song Chi-yul, a veteran of these raids, calls a greeting over his cup. Then an old friend appears — Bak, all smiles in his green puffer jacket. They shake hands, and Bak laughs that he only quit hunting because his wife is expecting their second son. Chi-yul admits that raiding for a fortune, like life itself, was never easy.

**candidate** `p0016_01, p0016_02, p0016_03, p0017_01, p0017_02`

Jin-Woo overhears the veterans whispering that he is actually the world's weakest hunter. Kim Sangshik tells Bak that the dungeon will be easy since the weakest man arrived. He tries to order coffee, but the vendor says the stand just ran out.

### Beat 8

**reference** `p0013_01, p0013_02, p0014_01`

Bak just sighs at that. Then the group perks up — Jin-Woo has arrived, and they thank him for coming. A colleague claps his shoulder about the cold, and he tells them he'll pull his weight again today.

**candidate** `p0018_02, p0018_03, p0018_04`

He sighs in disappointment as he walks away from the empty coffee stall. He realizes even the smallest comforts are out of reach for a man of his status. A voice suddenly screams that he is hurt again, breaking his quiet resignation.

### Beat 9

**reference** `p0014_02, p0014_03`

The truck regulars ask if he's even eaten yet — everyone is glad to see him. Watching all this warmth, Bak asks the obvious question: is this guy some kind of powerful hunter?

**candidate** `p0019_01`

Lee Joo-hee, the party's supporting healer, snaps at Jin-Woo. She asks him why his face is already injured yet again.

### Beat 10

**reference** `p0015_01, p0015_02, p0016_01, p0016_02, p0016_03`

Another hunter sets him straight — Bak wouldn't know the nickname, since Jin-Woo joined right after he quit. Within earshot, the older hunters trade it like gossip: the weakest hunter in the guild. One asks if he's really the weakest; the other says he is, and that their dungeon must be a weak one since he was assigned to it. Then they hush each other, in case he can hear.

**candidate** `p0020_01, p0020_02, p0020_03, p0021_01, p0021_02`

Sitting on wooden pallets, Jin-Woo explains that he went to the hospital for his face. He tells Lee Joo-hee that he was the only one injured during the last mission. The high-ranked hunters skipped a healer because they felt safe enough to leave him behind.

### Beat 11

**reference** `p0017_01, p0017_02`

He hears every word of it, and lets it pass. At the supply stand he asks for a cup of coffee, and the attendant apologizes — they've just run out.

**candidate** `p0022_01, p0022_02, p0022_03`

Jin-Woo smiles weakly and tells Lee Joo-hee that he is accustomed to being weak. She offers him a sympathetic look while they watch the others gather for the hunt. The weight of his debt remains heavy as they move toward the site entrance.

### Beat 12

**reference** `p0018_02, p0018_03`

Not even coffee today, he mutters — it feels like a bad sign. The attendant apologizes again, and he waves it off as nothing.

**candidate** `p0022_04, p0023_01`

Song Chi-yul, the veteran party leader, stands before the gathered hunters with a confident smile. He asks the raid party for permission to lead them through the upcoming dungeon.

### Beat 13

**reference** `p0018_04, p0019_01, p0020_01`

Lee Joo-hee, the party's healer, spots him across the lot and comes running — he's hurt again, she says, alarmed. He laughs it off, but she isn't buying it, and asks why his face keeps getting hurt.

**candidate** `p0024_01, p0024_02, p0024_03, p0025_01`

Kim Sangshik crosses his arms and smiles, agreeing to the choice of leader. Bak, another supporting hunter, nods and adds that they can easily trust the veteran's abilities. A hunter and a hunter happily agree to join. Jin-Woo smiles modestly next to Lee Joo-hee as they look forward.

### Beat 14

**reference** `p0020_02, p0020_03, p0021_01`

They sit together on a stack of lumber while she asks if he actually saw a doctor this time. He admits he did. Joo-hee is stunned to learn he was the only one on his last team who got hurt at all.

**candidate** `p0026_01, p0026_02, p0026_03, p0027_01`

Kim Sangshik tells the boy to stay safely behind the others because of his wounds. Jin-Woo resolves to do his best today as he and Lee Joo-hee enter the gate. Whether he will survive the new D-rank dungeon raid is the only question worth asking.

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
