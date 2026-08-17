# Script comparison — gold (hand-written) vs generated

Gold: `reference/ch1_gold_script.md` · Candidate: `projects/solo-leveling-ch1/script.json`

## Metrics (the target is the GOLD column, not 'better than last run')

| metric | gold | candidate |
|---|---|---|
| beats | 17 | 18 |
| words | 677 | 625 |
| avg_sentence_words | 15.0 | 14.9 |
| caption_markers_per_100w | 0.0 | 0.48 |
| speech_verbs_per_100w | 3.25 | 2.56 |
| connectives_per_100w | 3.69 | 3.36 |
| max_consecutive_pronoun_starts | 2 | 2 |
| pronoun_start_fraction | 0.2 | 0.33 |

## Side by side

### Beat 1

**GOLD** (p0002_01, p0003_01, p0004_01, p0005_01, p0006_01):
> Sung Jin-Woo lies in a pool of his own blood, barely able to move. Three towering, glowing-eyed guardians close in on him, weapons raised. A voice brands him the weakest hunter alive. He refuses to believe it, even as the blade comes down again.

**GEN** (p0002_01, p0003_01, p0004_01):
> Sung Jin-Woo, the world's weakest hunter, lies in his own blood while massive stone sentinels loom above. He gasps that he never expected this fate for an E-Rank, the lowest tier of power, though this day actually began hours earlier.

### Beat 2

**GOLD** (p0007_04):
> Then the sky clears, over present-day Seoul.

**GEN** (p0005_01, p0006_01, p0007_01, p0007_04):
> The massive stone sentinel looms over him while raising a heavy spear. He gasps for air and snaps a curse as the weapon plunges down in a spray of blood.

### Beat 3

**GOLD** (p0008_01, p0008_02):
> Jin-Woo walks the morning streets with fresh bandages on his face, just another commuter nobody looks at twice.

**GEN** (p0008_01, p0008_02, p0009_01, p0009_02):
> He walks the morning streets with fresh bandages on his face, just another commuter nobody looks at twice. He reflects that hunting is a job where his life is on the line and today is a work day. Within a Seoul construction site, a blue gate, a portal to another dimension, pulses inside the scaffolding.

### Beat 4

**GOLD** (p0009_01, p0009_02):
> Hunting is a job where your life is on the line, and today is a work day. A gate has torn open inside a construction site across town, and hunters are already gathering at the barriers.

**GEN** (p0010_01, p0010_03, p0010_04, p0011_01, p0011_02):
> A vibrating blue portal glows inside the scaffolding. Kim Sangshik, a veteran hunter wearing a blue jacket, stands by a food truck and grabs a hot coffee. He then sits down to chat with Song Chi-yul, a raid party leader wearing a blue jacket with tan trim, before hearing his name called out.

### Beat 5

**GOLD** (p0010_01, p0010_03):
> Inside the scaffolding, the gate hangs glowing blue. At the food truck below, Jin-Woo runs the same math as always — his mother's hospital bills against what the guild pays him.

**GEN** (p0012_01, p0012_02, p0012_03):
> Bak, a returning hunter, waves and greets Kim Sangshik after a long absence. Shaking hands, Kim asks why he returned to the job. Bak admits his wife is pregnant, so Kim muses that people raid, or hunt monsters for profit, to survive.

### Beat 6

**GOLD** (p0010_04, p0011_01):
> The truck sends a hunter off with a wish of luck for the raid, while two more grab a quick meal before heading in.

**GEN** (p0013_01, p0013_02):
> Bak closes his eyes and exhales a weary sigh. He says his situation only worsened after he decided to take a break.

### Beat 7

**GOLD** (p0011_02, p0012_01, p0012_02, p0012_03):
> Song Chi-yul, a veteran of these raids, calls a greeting over his cup. Then an old friend appears — Bak, all smiles in his green puffer jacket. They shake hands, and Bak laughs that he only quit hunting because his wife is expecting their second son. Chi-yul admits that raiding for a fortune, like life itself, was never easy.

**GEN** (p0014_01, p0014_02, p0014_03):
> Jin-Woo walks through the gated site where a friendly hunter places a hand on his shoulder. He laughs as Kim Sangshik waves from the background, prompting Bak to wonder if this popular newcomer is a powerful high-rank hunter.

### Beat 8

**GOLD** (p0013_01, p0013_02, p0014_01):
> Bak just sighs at that. Then the group perks up — Jin-Woo has arrived, and they thank him for coming. A colleague claps his shoulder about the cold, and he tells them he'll pull his weight again today.

**GEN** (p0015_01, p0015_02):
> Bak watches the young man walk past into the distance. Kim Sangshik smiles knowingly, preparing to explain that his nickname became famous after the other man quit.

### Beat 9

**GOLD** (p0014_02, p0014_03):
> The truck regulars ask if he's even eaten yet — everyone is glad to see him. Watching all this warmth, Bak asks the obvious question: is this guy some kind of powerful hunter?

**GEN** (p0016_01, p0016_02, p0016_03):
> Kim Sangshik laughs, confirming the rumors that Jin-Woo is actually the world's weakest hunter. He jokes that a weak party member ensures a safe dungeon. Overhearing the gossip, the protagonist looks downcast while walking past the heavy machinery.

### Beat 10

**GOLD** (p0015_01, p0015_02, p0016_01, p0016_02, p0016_03):
> Another hunter sets him straight — Bak wouldn't know the nickname, since Jin-Woo joined right after he quit. Within earshot, the older hunters trade it like gossip: the weakest hunter in the guild. One asks if he's really the weakest; the other says he is, and that their dungeon must be a weak one since he was assigned to it. Then they hush each other, in case he can hear.

**GEN** (p0017_01, p0017_02):
> Kim Sangshik and Bak chatter in the background. Jin-Woo sighs, muttering to himself that he can hear the older men gossiping.

### Beat 11

**GOLD** (p0017_01, p0017_02):
> He hears every word of it, and lets it pass. At the supply stand he asks for a cup of coffee, and the attendant apologizes — they've just run out.

**GEN** (p0018_02, p0018_03, p0018_04):
> He turns from the counter empty-handed, saying that missing out on coffee feels terrible. The association worker behind the desk calls after him, but he simply walks away. He quickly tells the clerk that everything is fine before moving on.

### Beat 12

**GOLD** (p0018_02, p0018_03):
> Not even coffee today, he mutters — it feels like a bad sign. The attendant apologizes again, and he waves it off as nothing.

**GEN** (p0019_01, p0020_01, p0020_02):
> Lee Joo-hee, the party's rookie healer, shouts that his facial wounds are the real problem today. They sit on wooden pallets while she asks if he visited a hospital, and he confirms that he did.

### Beat 13

**GOLD** (p0018_04, p0019_01, p0020_01):
> Lee Joo-hee, the party's healer, spots him across the lot and comes running — he's hurt again, she says, alarmed. He laughs it off, but she isn't buying it, and asks why his face keeps getting hurt.

**GEN** (p0020_03, p0021_01, p0021_02):
> Jin-Woo admits he was the only one hurt because the high-ranked party members refused to bring a healer. Lee Joo-hee snaps that they only skipped the support because they felt safe themselves.

### Beat 14

**GOLD** (p0020_02, p0020_03, p0021_01):
> They sit together on a stack of lumber while she asks if he actually saw a doctor this time. He admits he did. Joo-hee is stunned to learn he was the only one on his last team who got hurt at all.

**GEN** (p0022_01, p0022_02, p0022_03):
> Jin-Woo offers a resigned smile, admitting his weakness makes these constant injuries a normal occurrence. He stands to leave as Lee Joo-hee watches him go with a deeply sorrowful gaze.

### Beat 15

**GOLD** (p0021_02, p0022_01, p0022_02, p0022_03):
> The rest of his party outranked him badly enough that they skipped bringing a healer at all, he explains. Joo-hee asks why that would matter, if it's only their own safety they cared about. He shrugs it off with a tired smile. It's only because he's weak, he says, and he's used to it by now. She goes quiet, and the two of them head back toward the group.

**GEN** (p0022_04, p0023_01):
> Jin-Woo joins the crowd near the portal as Song Chi-yul asks to take charge of the raid party.

### Beat 16

**GOLD** (p0022_04, p0023_01, p0024_01, p0024_02):
> The full party gathers at the gate as Chi-yul modestly asks the group to let him lead the raid. The others back him without hesitation — he's the highest-ranked among them, one says, and worth trusting. Jin-Woo and Joo-hee greet him and ask him to look after the group.

**GEN** (p0024_01, p0024_02, p0024_03):
> Kim Sangshik crosses his arms in the cold, calling the raid leader the highest-ranked hunter present. Bak smiles in agreement and says they can easily trust the veteran's impressive combat skills.

### Beat 17

**GOLD** (p0024_03, p0025_01, p0026_01, p0026_02, p0026_03, p0027_01):
> Chi-yul tells the group to head in, and they answer eager and ready. He promises to keep the injured Jin-Woo safely behind the front line, and Jin-Woo laughs along, no argument left in him. Kim Sang-shik scowls, uneasy, as they near the entrance. Someone calls Jin-Woo forward — okay, okay, he says — and he steps into the blinding blue light of the gate, and disappears.

**GEN** (p0025_01, p0026_01, p0026_03):
> The hunters roar with excitement while approaching the glowing portal to begin their raid. Kim Sangshik tells Jin-Woo to stay safely behind everyone due to his injuries. He laughs sheepishly before his expression hardens, vowing that today will be different.

### Beat 18

**GOLD** ():
> (no gold beat)

**GEN** (p0026_02, p0027_01):
> Lee Joo-hee tells Jin-Woo that they should go. He replies that he is ready and follows her through the glowing gate. Swirling light surrounds him as he steps completely into the blue portal.
