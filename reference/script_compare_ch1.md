# Script comparison — gold (hand-written) vs generated

Gold: `reference/ch1_gold_script.md` · Candidate: `projects/solo-leveling-ch1/script.json`

## Metrics (the target is the GOLD column, not 'better than last run')

| metric | gold | candidate |
|---|---|---|
| beats | 17 | 18 |
| words | 677 | 941 |
| avg_sentence_words | 15.0 | 14.5 |
| caption_markers_per_100w | 0.0 | 0.21 |
| speech_verbs_per_100w | 3.25 | 3.19 |
| connectives_per_100w | 3.69 | 2.44 |
| max_consecutive_pronoun_starts | 2 | 2 |
| pronoun_start_fraction | 0.2 | 0.2 |

## Side by side

### Beat 1

**GOLD** (p0002_01, p0003_01, p0004_01, p0005_01, p0006_01):
> Sung Jin-Woo lies in a pool of his own blood, barely able to move. Three towering, glowing-eyed guardians close in on him, weapons raised. A voice brands him the weakest hunter alive. He refuses to believe it, even as the blade comes down again.

**GEN** (p0002_01, p0003_01, p0004_01, p0005_01):
> Sung Jin-Woo struggles to breathe through his injuries as he admits he is only an E-Rank hunter. His own blood pools across the cold stone floor while he sits entirely defeated. Two massive statues tower over him, sealing his fate as the weakest of them all. Suddenly, a silhouette prepares to strike, and his bloodshot eye stares back in terror.

### Beat 2

**GOLD** (p0007_04):
> Then the sky clears, over present-day Seoul.

**GEN** (p0006_01, p0007_01, p0007_04):
> He clenches his teeth in agony and curses his fate as the massive statues strike. That's where this day is headed, but it starts hours earlier on a bright, peaceful morning in the city.

### Beat 3

**GOLD** (p0008_01, p0008_02):
> Jin-Woo walks the morning streets with fresh bandages on his face, just another commuter nobody looks at twice.

**GEN** (p0008_01, p0008_02, p0009_01, p0009_02):
> Sung Jin-Woo walks through a busy urban street in the present day. A blonde pedestrian passes by as crowds of commuters move toward a nearby shopfront. Walking down the busy sidewalk, he contemplates a dangerous job where his life is constantly on the line. This risky path leads him directly to an active construction site in Seoul. Heavy machinery operates around the area while mysterious blue lights glow brightly in the dust.

### Beat 4

**GOLD** (p0009_01, p0009_02):
> Hunting is a job where your life is on the line, and today is a work day. A gate has torn open inside a construction site across town, and hunters are already gathering at the barriers.

**GEN** (p0010_01, p0010_03, p0010_04, p0011_01, p0011_02):
> A blue gate pulses with light behind metal scaffolding at a noisy construction site. Nearby, Kim Sangshik, a seasoned hunter with short grey hair, finishes his meal at a mobile food truck. Earnings from these dangerous raids help hunters pay off heavy medical bills. The food stand vendor hands the veteran a hot drink and wishes him luck on the raid. He replies with a quiet word of thanks as he accepts the warm cup. An empty plate and chopsticks rest on the counter as he prepares to leave. Suddenly, a loud voice calls out his name before he can take a sip.

### Beat 5

**GOLD** (p0010_01, p0010_03):
> Inside the scaffolding, the gate hangs glowing blue. At the food truck below, Jin-Woo runs the same math as always — his mother's hospital bills against what the guild pays him.

**GEN** (p0012_01, p0012_02, p0012_03):
> Bak, the curly-haired former hunter, smiles and waves to his old acquaintances. A uniformed gate guard asks what he is doing back at the dungeons. Kim Sangshik, the man with short grey hair and a blue jacket, warmly shakes his hand. Kim asks why his friend returned to this dangerous work after quitting. Bak laughs and replies that his wife is pregnant with their second son. With a weary expression, Kim says that life is never easy. Still, they must continue to raid if they want to make a fortune.

### Beat 6

**GOLD** (p0010_04, p0011_01):
> The truck sends a hunter off with a wish of luck for the raid, while two more grab a quick meal before heading in.

**GEN** (p0013_01, p0013_02):
> Bak, a curly-haired former hunter, closes his eyes and exhales a heavy sigh. He says his situation is only worse after taking a break. Listening nearby, Kim Sangshik, a veteran with short grey hair, drinks from a blue cup. He then spots Jin-Woo, greeting the youth warmly and thanking him for coming.

### Beat 7

**GOLD** (p0011_02, p0012_01, p0012_02, p0012_03):
> Song Chi-yul, a veteran of these raids, calls a greeting over his cup. Then an old friend appears — Bak, all smiles in his green puffer jacket. They shake hands, and Bak laughs that he only quit hunting because his wife is expecting their second son. Chi-yul admits that raiding for a fortune, like life itself, was never easy.

**GEN** (p0014_01, p0014_02, p0014_03):
> Jin-Woo walks through the crowd of hunters as a man in a green jacket pats his shoulder. The friendly hunter says it is freezing, and he replies humbly that he hopes for a good raid. Then, Kim Sangshik, a hunter with short grey hair, waves and asks if he has eaten yet. Nearby, a bystander with dark curly hair watches this greeting and wonders if he is secretly powerful.

### Beat 8

**GOLD** (p0013_01, p0013_02, p0014_01):
> Bak just sighs at that. Then the group perks up — Jin-Woo has arrived, and they thank him for coming. A colleague claps his shoulder about the cold, and he tells them he'll pull his weight again today.

**GEN** (p0015_01, p0015_02):
> Bak, a former hunter, points toward Jin-Woo as he walks away. Kim Sangshik, a man with short grey hair, smiles while talking to another hunter nearby. He says they missed his arrival and prepares to reveal his infamous nickname.

### Beat 9

**GOLD** (p0014_02, p0014_03):
> The truck regulars ask if he's even eaten yet — everyone is glad to see him. Watching all this warmth, Bak asks the obvious question: is this guy some kind of powerful hunter?

**GEN** (p0016_01, p0016_02, p0016_03):
> Jin-Woo walks past the heavy machinery while whispers about his notorious title echo behind him. Hearing the nickname of the world's weakest, Bak, a curly-haired former hunter, asks if it is true. Kim Sangshik, a veteran hunter with short grey hair, replies that he is indeed the absolute weakest. Overhearing their laughter, he merely sighs and keeps walking.

### Beat 10

**GOLD** (p0015_01, p0015_02, p0016_01, p0016_02, p0016_03):
> Another hunter sets him straight — Bak wouldn't know the nickname, since Jin-Woo joined right after he quit. Within earshot, the older hunters trade it like gossip: the weakest hunter in the guild. One asks if he's really the weakest; the other says he is, and that their dungeon must be a weak one since he was assigned to it. Then they hush each other, in case he can hear.

**GEN** (p0017_01, p0017_02):
> He walks away from the mocking group and asks a guard for coffee, but the man says they already ran out.

### Beat 11

**GOLD** (p0017_01, p0017_02):
> He hears every word of it, and lets it pass. At the supply stand he asks for a cup of coffee, and the attendant apologizes — they've just run out.

**GEN** (p0018_02, p0018_03, p0018_04):
> He sighs, realizing his luck is so bad he cannot even get a coffee. The gate guard wearing a blue cap asks about a past incident, but he says it is fine until a sudden shout startles him.

### Beat 12

**GOLD** (p0018_02, p0018_03):
> Not even coffee today, he mutters — it feels like a bad sign. The attendant apologizes again, and he waves it off as nothing.

**GEN** (p0019_01, p0020_01, p0020_02):
> Lee Joo-hee, a young woman with long orange hair, shouts in deep frustration. Jin-Woo merely rubs his neck and offers a sheepish, awkward smile in return. Sitting together on some construction crates, the pair watch the busy workers pass them by. She asks if his injuries forced him to go to the hospital, and he replies that they did.

### Beat 13

**GOLD** (p0018_04, p0019_01, p0020_01):
> Lee Joo-hee, the party's healer, spots him across the lot and comes running — he's hurt again, she says, alarmed. He laughs it off, but she isn't buying it, and asks why his face keeps getting hurt.

**GEN** (p0020_03, p0021_01, p0021_02):
> Lee Joo-hee stares in disbelief. Jin-Woo admits the higher-ranked hunters skipped hiring a proper healer because they felt safe. He looks down as she snaps at their foolishness, realizing they left him to pay for their arrogance.

### Beat 14

**GOLD** (p0020_02, p0020_03, p0021_01):
> They sit together on a stack of lumber while she asks if he actually saw a doctor this time. He admits he did. Joo-hee is stunned to learn he was the only one on his last team who got hurt at all.

**GEN** (p0022_01, p0022_02, p0022_03):
> Jin-Woo gives a melancholic smile and says he is already used to the pain of being weak. Lee Joo-hee watches him in somber silence. Still, he stands and walks toward the glowing gate, ready for the job.

### Beat 15

**GOLD** (p0021_02, p0022_01, p0022_02, p0022_03):
> The rest of his party outranked him badly enough that they skipped bringing a healer at all, he explains. Joo-hee asks why that would matter, if it's only their own safety they cared about. He shrugs it off with a tired smile. It's only because he's weak, he says, and he's used to it by now. She goes quiet, and the two of them head back toward the group.

**GEN** (p0022_04, p0023_01):
> A crowd of hunters gathers in front of the massive, glowing blue portal. Song Chi-yul, an older veteran hunter with short grey hair, addresses the group with his hands on his hips, asking to lead the raid.

### Beat 16

**GOLD** (p0022_04, p0023_01, p0024_01, p0024_02):
> The full party gathers at the gate as Chi-yul modestly asks the group to let him lead the raid. The others back him without hesitation — he's the highest-ranked among them, one says, and worth trusting. Jin-Woo and Joo-hee greet him and ask him to look after the group.

**GEN** (p0024_01, p0024_02, p0024_03):
> Kim Sangshik, a seasoned hunter, says their leader has the highest rank. Bak, a former hunter, replies that he trusts their leader's skills. Another hunter quickly says that he also agrees with the choice. Jin-Woo smiles and tells Lee Joo-hee, the party's rookie healer, that their leader will protect them.

### Beat 17

**GOLD** (p0024_03, p0025_01, p0026_01, p0026_02, p0026_03, p0027_01):
> Chi-yul tells the group to head in, and they answer eager and ready. He promises to keep the injured Jin-Woo safely behind the front line, and Jin-Woo laughs along, no argument left in him. Kim Sang-shik scowls, uneasy, as they near the entrance. Someone calls Jin-Woo forward — okay, okay, he says — and he steps into the blinding blue light of the gate, and disappears.

**GEN** (p0025_01, p0026_01, p0026_02):
> The raid leader shouts a signal, rallying the hunters as they march toward the glowing blue dungeon gate. Kim Sangshik, a senior hunter with short grey hair, smiles warmly to ease the tension. His silent reassurance gives Jin-Woo the courage to step forward. Alongside him, Lee Joo-hee, the party's rookie healer, crosses the threshold into the unknown dungeon.

### Beat 18

**GOLD** ():
> (no gold beat)

**GEN** (p0026_03, p0027_01):
> He takes a deep breath to steel his nerves. He is the world's weakest hunter, yet the gate swallows him for a raid he might not survive.
