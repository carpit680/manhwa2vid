# Script comparison — reference vs generated

Reference: `reference/frozen_player/ch1-2_gold_script.md` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.51** of 357 salient reference terms
- order_tau: **0.35** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): deep, cavern, lone, swordsman, steps, etched, snowflakes, brands, encountered, descends, crowned, silhouette, gown, feels, abandoning, doesn't, bait, aren't, drawing, killing, he'll, ignorant, works, conjures, pure

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 25 | 28 |
| words | 1048 | 1436 |
| avg_sentence_words | 13.1 | 13.7 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 1.24 | 2.79 |
| connectives_per_100w | 2.39 | 2.99 |
| max_consecutive_pronoun_starts | 5 | 3 |
| pronoun_start_fraction | 0.2 | 0.31 |

## Side by side

### Beat 1

**reference** 

Deep inside an ice cavern, a lone swordsman in black steps onto a frozen floor
etched with snowflakes. A system message brands the moment: he has encountered
the Frost Queen. She descends from her throne of ice, a crowned silhouette in a
gown of frost, and asks how it feels to stand here after abandoning his
comrades to die.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07, p0002_01, p0002_02, p0002_03, p0002_04, p0002_05, p0002_06`

Seo Jun-Ho, legendary hero, enters the throne room as his blade glows with power. A system alert confirms his arrival at the Antarctic gate, a supernatural dungeon portal, where the Frost Queen mocks him. He warns his comrades will not die easily and tells her to shut it.

### Beat 2

**reference** 

He doesn't take the bait. His friends aren't the kind to die that easily, he
says, drawing a glowing blade — if killing her ends this, he'll do it here.
She only laughs, calling him ignorant of how this world really works. He tells
her to be quiet. He has no time to waste.

**candidate** `p0002_09, p0002_10, p0002_11, p0003_01, p0003_02, p0003_03`

A boot shatters the frozen floor as Jun-Ho and the Frost Queen collide. These warriors trade rapid blows in the throne room, showering the chamber in brilliant sparks of energy. He braces himself as a massive burst of ice magic suddenly pushes him backward.

### Beat 3

**reference** 

The queen conjures a sword of pure ice, and they collide in midair. The duel
tears the throne room apart — ice shards, black flashes, magic detonating off
the walls. She hurls a point-blank blast; he slips past it by a breath.

**candidate** `p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

The Frost Queen smiles while gathering a lethal surge of freezing magic in her palm. Jun-Ho thinks this is impossible just before a blinding explosion tears through the room. He drops into a low crouch while jagged ice shards and dark energy swirl around him. A faint blue light flickers as he stands over his defeated opponent.

### Beat 4

**reference** 

One final exchange, and the hall falls silent. The Frost Queen kneels, beaten.
She admits she had fun. He can't say the same. But before his blade can finish
it, her body begins to glow — and the ice turns on him, crawling up his arms.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10, p0005_11`

The Frost Queen begins to dissolve into light and admits the battle was fun. Jun-Ho stares her down and replies that he cannot say the same. He delivers a final strike but gasps as creeping frost suddenly climbs his skin. A system alert declares his hibernation is mandatory to absorb her nucleus, a monster's core.

### Beat 5

**reference** 

A system message explains the price: he is absorbing the Frost Queen's power,
and his body will hibernate until her nucleus is fully absorbed. Frost swallows
him whole, sword still in hand.

**candidate** `p0005_12, p0005_14, p0006_02, p0006_03, p0006_04, p0006_05, p0006_06, p0006_07, p0006_08, p0006_09`

Twenty-five years ago in Antarctica, the five-member hero party reached the final dungeon doorway only for a system message to declare that only one person could proceed. Khali, the tattooed giant of the original five-member hero party, punches the ice wall in immense frustration.

### Beat 6

**reference** 

Seventy-six hours earlier, in Antarctica, five hunters stand at the mouth of
humanity's final dungeon — the Frost Queen's Nest. The rule carved into it is
simple and cruel: only one person may climb the stairs.

**candidate** `p0007_02, p0007_03, p0007_04, p0007_05, p0007_06, p0007_07`

A frustrated click of the tongue rings out as Khali clenches his jaw. He admits his resentment but yields because no hunter matches the strength of Jun-Ho. The swordswoman, the party's front-line fighter, teases him for yielding so fast. She remains serious while agreeing their legendary ally must be the one to go.

### Beat 7

**reference** 

Khali, a mountain of a man in tattoos, punches the ice wall — sending one
person up alone means telling the other four to die. Skaya, the party's
white-haired healer, calms him: time is short, and she believes Specter should
be the one to go.

**candidate** `p0007_08, p0007_09, p0007_10, p0007_11, p0008_02, p0008_03`

Jun-Ho stands a short distance away from his four trusted companions. He looks at Khali and Skaya. Beside them stand the marksman and the swordswoman. He asks the group if they are sure they will not regret their decision. A voice questions if regret is even possible.

### Beat 8

**reference** 

The cowboy-hatted marksman agrees — against an ice monster, everyone but
Specter fights at a disadvantage. Khali concedes there's no one quite like
him. The swordswoman closes it: it's best if Specter goes.

**candidate** `p0008_04, p0008_05, p0008_06, p0008_07, p0008_08, p0008_09`

Skaya smiles while clutching her staff and tells Jun-Ho that their deaths will not be in vain. He thinks of his comrades as they apologize for the heavy burden they are leaving him. They stand together one last time and insist that only he can finish this fight.

### Beat 9

**reference** 

Specter asks if they're sure they won't regret this. The marksman shrugs —
they might, if he loses and their deaths mean nothing. But they trust him.
Skaya smiles and says she knows he won't let their deaths be in vain.

**candidate** `p0008_10, p0008_11, p0008_12, p0008_13, p0009_01, p0009_02, p0009_03, p0009_04, p0009_05, p0009_06`

Twenty-five years pass, and the narrative shifts to a modern exhibition hall where a presenter in a black suit details the historical terror of the Frost Queen. When a schoolboy asks about the legendary expedition team, the presenter snaps his fingers to unveil the five frozen heroes, including Jun-Ho, preserved in solid ice.

### Beat 10

**reference** 

All he can manage is a quiet "you guys." Alone on the stairs, their voices at
his back — if it's you, you can do this — he whispers an apology and climbs.

**candidate** `p0009_07, p0009_08, p0009_09, p0009_10, p0010_03, p0010_04`

A frozen hand twitches as the schoolboy shouts that the statue is moving. Dismissing his claim as a mistake, the presenter turns away. The monument of him shatters into jagged pieces while his teammates remain frozen. She gasps that such an event is impossible.

### Beat 11

**reference** 

Twenty-five years later, under a clear Seoul sky, a lecture hall is learning
about the monsters humanity never beat. The presenter recounts how the Frost
Queen froze the Pacific with a wave of her hand — and how the Nest Attack
Team, the Five Heroes, went to Antarctica to stop her.

**candidate** `p0010_05, p0010_06, p0010_08, p0011_01, p0011_02`

He bursts violently from his frozen prison as the central ice monument explodes. He tumbles through a shower of flying shards and falls toward the museum floor. Collapsing onto the hard ground, he shivers intensely among the scattered remnants of ice. Shuddering from the sudden warmth, he finally breathes the outside air and mutters that it is cold.

### Beat 12

**reference** 

On stage stands their memorial: five figures sculpted in ice. Then a boy in
the audience starts shouting — the statue just moved. The presenter laughs it
off, until the cracking starts behind her.

**candidate** `p0011_03, p0011_04, p0011_05, p0011_06, p0012_01, p0012_02, p0012_03`

The presenter asks what is happening as a notification confirms Jun-Ho received the EX-rank Frost skill. While news screens announce the Specter has returned, he sits in a hospital bed. He asks Shim Deok-gu, the Player Association president, if twenty-five years have really passed. Studying his trembling fingers, he admits he can barely clench his hands.

### Beat 13

**reference** 

The ice explodes. A young man collapses out of the shards, steaming with
cold, and a system message finally updates: absorption one hundred percent.
Congratulations. The Frost Queen's nucleus is his, and a new skill with it —
Frost, EX rank.

**candidate** `p0012_04, p0012_07, p0012_09, p0012_10, p0012_12, p0012_14`

He clenches his trembling hands, testing the limits of his weakened body. The chief doctor, the hospital’s lead physician, enters to announce that the Association president is arriving. He chuckles and thanks the man while admitting that very few people would still call him a friend.

### Beat 14

**reference** 

His first words in twenty-five years: "Co... cold." As staff rush the stage,
the weakest whisper in the hall belongs to the strongest player alive. The
Frozen Player has returned.

**candidate** `p0013_01, p0013_02, p0013_03, p0013_04, p0013_05, p0013_07`

He gazes through the glass at the towering skyscrapers of a world he barely recognizes. Even as the city thrives, he cannot ignore the heavy silence of the friends he left behind.

### Beat 15

**reference** 

The news breaks worldwide: the legend is awake, the Specter who felled the
Frost Queen, back after twenty-five years of cryogenic sleep. The man himself
sits in a hospital bed scrolling headlines, muttering that it's really been
that long. He can barely close his shaking hand into a fist.

**candidate** `p0013_08, p0013_12, p0013_15, p0013_16, p0013_17, p0013_18`

Jun-Ho holds his signature mask, weighing the cost of hiding his face again. He leaves it lowered as the chief doctor enters and stammers the name Specter. Awed by the sight, the physician asks why the legend would finally reveal his appearance. The young doctor, a junior resident, and the nurse, a clinic assistant, freeze in shock.

### Beat 16

**reference** 

A doctor announces the president of the Player Association is on his way.
Jun-Ho isn't interested in strangers — but this one, they say, is an old
friend. He takes off his mask to the staff's disbelief and waits.

**candidate** `p0014_01, p0014_03, p0014_04, p0014_05, p0014_07, p0014_08`

Before the doctors can recover, Shim Deok-gu enters the room accompanied by his bodyguards. He requests a private conversation with Jun-Ho, prompting the awestruck hospital staff to bow and leave the room immediately.

### Beat 17

**reference** 

The president arrives flanked by suits, and one look is enough. Deok-gu — the
same voice, minus the hair. Jun-Ho bursts out laughing: he called that
M-pattern baldness twenty-five years ago. So much for a touching reunion.

**candidate** `p0014_09, p0014_10, p0014_11, p0015_01, p0015_02, p0015_03`

Shim Deok-gu marvels that Jun-Ho looks exactly as he did decades ago. Recognizing the familiar voice, he laughs and points out his friend's severe M-pattern baldness. The president snaps at the lack of respect while he calls it a touching reunion. Sighing, Deok-gu pulls up a chair and admits that he hasn't changed at all.

### Beat 18

**reference** 

Alone, Deok-gu lays out the missing years. When the Frost Queen fell, every
player heard the same message, and the world wept with joy — for about a
minute. Then a dimensional elevator rose in the Pacific: the second floor was
open, ten floors in all. Stay strong until the final floor.

**candidate** `p0015_04, p0015_06, p0015_07, p0015_08, p0016_05, p0016_06`

He shifts the conversation to a more serious topic. He prepares to share the difficult news of how the world changed. But his friend recalls that every player heard the exact same message. Twenty-five years ago, a system announcement declares the final boss defeated. Deok-gu shouts in joy that his companion finally won. Then, the system proclaims that safe zones will now appear across Earth.

### Beat 19

**reference** 

Jun-Ho does the math out loud — five years for one floor, so in twenty-five
they should be on the seventh. Deok-gu can barely say it: humanity has
cleared one. The third floor is a sea of lava, and the only thing that can
cool it is an altar that demands the Frost Queen's nucleus.

**candidate** `p0016_07, p0016_08, p0016_09, p0016_10, p0016_11, p0016_13`

The jubilant citizens rejoice in the streets, crying tears of joy over the hard-won victory. Yet he warns that the world does not let their relief last even for a single minute. A sudden chime rings as the system announces that a dimensional elevator is now installed in the Pacific Ocean. The startled audience members gasp in utter disbelief at the sudden notification.

### Beat 20

**reference** 

The nucleus they searched the Nest decades for. Jun-Ho goes very quiet,
because he knows exactly where it is — he absorbed it. With the straightest
face he can manage, he declares they were simply unlucky, and everyone should
be understanding about honest mistakes. Deok-gu is not.

**candidate** `p0016_16, p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04, p0017_05, p0017_06, p0017_07, p0017_10`

The system announced access to the Frontier Area, prompting global leaders and politicians to hold emergency meetings. Deok-gu explains that humanity conquered the second floor, gaining immense magic and resources, but Jun-Ho is shocked to learn that the Dimensional Elevator consists of ten floors. Based on the timeline, he calculates that they should have reached the seventh floor by now.

### Beat 21

**reference** 

That evening, Jun-Ho asks where his team ended up. The Seoul History Museum —
though Deok-gu warns the streets below are crawling with reporters. Which is
why, hours later, a hooded figure badges through a service door instead.

**candidate** `p0018_01, p0018_02, p0018_03, p0018_04, p0018_06, p0018_09`

Jun-Ho looks down solemnly while comparing the current era to his own past. Behind him stand the ghostly figures of his former comrades. He stands before the spirit of Khali. Beside him is Skaya. The marksman also stands there. Finally, the swordswoman joins them. He asks Shim Deok-gu their current floor. His old friend remains completely silent and looks down.

### Beat 22

**reference** 

He walks past a dragon's skeleton — annoyed they put that thing on display —
into a hall kept cold on purpose. There they are: his four friends, frozen
mid-stride, exhibited like trophies.

**candidate** `p0018_12, p0018_13, p0018_14, p0018_16, p0019_01, p0019_02`

Shim Deok-gu reveals their pathetic progress, and Jun-Ho collapses onto the mattress in total disbelief. Covering his face, he mutters that he has nothing to say after twenty-five wasted years. He bolts upright as a green aura flares, demanding how they only cleared the second floor.

### Beat 23

**reference** 

He sits down in front of them and apologizes for being late. Four paper cups,
one bottle shared with the dead — the world is a better place now, he tells
them; the peace they dreamed of held. So now... rest.

**candidate** `p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12`

Jun-Ho glares at a sweating Shim Deok-gu. He tells his old friend that he is listening only because he is curious. The two men face each other as the tension in the room grows heavy. But his fury only mounts, while the older man remains solemnly silent in the face of his anger.

### Beat 24

**reference** 

He can't finish the sentence. Brushing the dust from Skaya's ice, he mutters
that the alcohol tastes sweet. Then a system message cuts through the grief:
Frost EX confirmed — insufficient magic — seal removal failed.

**candidate** `p0019_13, p0020_01, p0020_02, p0020_03, p0020_04, p0020_05`

Shim Deok-gu says only certain players can withstand the magma. He tells Jun-Ho that they discovered an ancient altar floating in the lava. This altar requires the Frost Queen's Nucleus to cool the surrounding heat. Clutching his forehead, Deok-gu says they searched the Nest countless times without success.

### Beat 25

**reference** 

Seal. Not tomb. The message spells it out: with the Frost skill, the ice
holding his friends can be undone. They were never dead — and now the
strongest player in history, reduced to a shaking fist, has a reason to start
over. What?!

**candidate** `p0020_06, p0020_07, p0020_08, p0020_10, p0020_11, p0020_12, p0020_14, p0020_15`

Jun-Ho rests a hand on his friend's shoulder to ease the heavy guilt. He tells Shim Deok-gu that the players were simply unlucky and their failure was an understandable mistake. Deok-gu shouts in joyful disbelief at the kindness. Watching the outburst, he mutters a curse and offers an awkward, sweating smile.

### Beat 26

**reference** 

(no reference beat)

**candidate** `p0021_01, p0021_12, p0021_13, p0022_01, p0022_02, p0022_03, p0022_04, p0022_05, p0022_06, p0022_07`

Jun-Ho wonders how to break the news to his friend without triggering a massive lecture. Since Shim Deok-gu warns him about reporters waiting downstairs, he agrees to stay hidden. He enters the museum vault via biometric security and passes a displayed dragon skeleton. Reaching his frozen comrades, he sits and whispers an apology for being so late.

### Beat 27

**reference** 

(no reference beat)

**candidate** `p0023_01, p0023_02, p0023_04, p0023_05, p0023_06, p0023_07`

The museum vault is silent as he recalls their shared laughter. He tells his sleeping comrades the peace they dreamed of is finally safe. Liquid splashes into paper cups as he invites his friends to have a drink. Sitting on the floor, he tells the team they can finally rest.

### Beat 28

**reference** 

(no reference beat)

**candidate** `p0023_08, p0023_09, p0023_10, p0023_12, p0023_13, p0024_01, p0024_03`

Jun-Ho takes a slow drink of his alcohol and looks up at his frozen teammates. They stand bathed in a bright beam of light inside the quiet room. He gazes at the icy face of Skaya. He asks his silent friends if the sweet drink tastes good to them, then mutters a curse.
