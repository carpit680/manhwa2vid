# Script comparison — reference vs generated

Reference: `reference/frozen_player/ch1-2_gold_script.md` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.48** of 357 salient reference terms
- order_tau: **0.44** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): deep, cavern, swordsman, etched, snowflakes, brands, encountered, descends, crowned, silhouette, gown, feels, doesn't, bait, aren't, kind, easily, drawing, blade, killing, he'll, ignorant, works, waste, conjures

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 25 | 28 |
| words | 1048 | 1376 |
| avg_sentence_words | 13.1 | 14.3 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 1.24 | 2.18 |
| connectives_per_100w | 2.39 | 2.83 |
| max_consecutive_pronoun_starts | 5 | 2 |
| pronoun_start_fraction | 0.2 | 0.25 |

## Side by side

### Beat 1

**reference** 

Deep inside an ice cavern, a lone swordsman in black steps onto a frozen floor
etched with snowflakes. A system message brands the moment: he has encountered
the Frost Queen. She descends from her throne of ice, a crowned silhouette in a
gown of frost, and asks how it feels to stand here after abandoning his
comrades to die.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07, p0002_01, p0002_02, p0002_03, p0002_04, p0002_05, p0002_06`

Seo Jun-Ho, enters the Frost Queen's Nest as the system confirms the icy ruler's presence. Frost Queen, the final boss of the Antarctic gate, mocks him for abandoning his comrades. He snaps that they will not die and tells her to shut it before promising her certain death.

### Beat 2

**reference** 

He doesn't take the bait. His friends aren't the kind to die that easily, he
says, drawing a glowing blade — if killing her ends this, he'll do it here.
She only laughs, calling him ignorant of how this world really works. He tells
her to be quiet. He has no time to waste.

**candidate** `p0002_09, p0002_10, p0002_11, p0003_01, p0003_02, p0003_03`

Jun-Ho steps firmly onto the ice, shattering the frozen floor beneath his weight. He lunges into the air to meet the Frost Queen as their powers collide with blinding force. Rapid blows echo through the throne room, leaving dark and light energy trails in their wake. A massive burst of ice suddenly pushes him back.

### Beat 3

**reference** 

The queen conjures a sword of pure ice, and they collide in midair. The duel
tears the throne room apart — ice shards, black flashes, magic detonating off
the walls. She hurls a point-blank blast; he slips past it by a breath.

**candidate** `p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

The Frost Queen smiles and gathers a lethal surge of magic in her palm. Jun-Ho gasps as the chamber vanishes in a blinding explosion. He lands in a low crouch, and shards of the floor rain around him. He stands before the defeated ruler in her crystalline throne room.

### Beat 4

**reference** 

One final exchange, and the hall falls silent. The Frost Queen kneels, beaten.
She admits she had fun. He can't say the same. But before his blade can finish
it, her body begins to glow — and the ice turns on him, crawling up his arms.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10, p0005_11, p0005_12, p0005_14, p0006_02, p0006_03, p0006_04`

After Jun-Ho delivers a final strike, ice rapidly grows over him to begin his long hibernation, transitioning back to Antarctica twenty-five years ago where Khali, the tattooed giant of the original five-member hero party, punches an ice wall in frustration.

### Beat 5

**reference** 

A system message explains the price: he is absorbing the Frost Queen's power,
and his body will hibernate until her nucleus is fully absorbed. Frost swallows
him whole, sword still in hand.

**candidate** `p0006_05, p0006_06, p0006_07, p0006_08, p0006_09, p0007_02, p0007_03`

Skaya, the white-haired healer of the original five-member hero party, and the marksman, the long-range attacker of the original five-member hero party, tell him that he must go alone due to their elemental disadvantages.

### Beat 6

**reference** 

Seventy-six hours earlier, in Antarctica, five hunters stand at the mouth of
humanity's final dungeon — the Frost Queen's Nest. The rule carved into it is
simple and cruel: only one person may climb the stairs.

**candidate** `p0007_04, p0007_05, p0007_06, p0007_07, p0007_08, p0007_09, p0007_10, p0007_11`

Khali concedes his spot to let his friend proceed, and his teammates assure him that they trust him completely, knowing he will not let them die in vain.

### Beat 7

**reference** 

Khali, a mountain of a man in tattoos, punches the ice wall — sending one
person up alone means telling the other four to die. Skaya, the party's
white-haired healer, calms him: time is short, and she believes Specter should
be the one to go.

**candidate** `p0008_02, p0008_03, p0008_04, p0008_05, p0008_06, p0008_07`

Skaya warmly smiles and reminds Jun-Ho that she trusts him to succeed, leaving him to stare forward silently.

### Beat 8

**reference** 

The cowboy-hatted marksman agrees — against an ice monster, everyone but
Specter fights at a disadvantage. Khali concedes there's no one quite like
him. The swordswoman closes it: it's best if Specter goes.

**candidate** `p0008_08, p0008_09, p0008_10, p0008_11, p0008_12, p0008_13`

Jun-Ho faces his somber teammates during their final moments together. Skaya apologizes to him. Khali tells him that he can succeed. Beside them, the marksman remains silent. Twenty-five years pass in an instant under a clear, bright sky. A modern white building stands on a grassy hill in the present day.

### Beat 9

**reference** 

Specter asks if they're sure they won't regret this. The marksman shrugs —
they might, if he loses and their deaths mean nothing. But they trust him.
Skaya smiles and says she knows he won't let their deaths be in vain.

**candidate** `p0009_01, p0009_02, p0009_03, p0009_04, p0009_05, p0009_06`

Inside a dark museum auditorium, a schoolboy, a young student, asks the presenter about the Nest Attack Team. The man, a museum guide, replies that the boy is correct and snaps his fingers. Stage lights illuminate Seo Jun-Ho and his frozen teammates as he introduces them as the legendary Five Heroes.

### Beat 10

**reference** 

All he can manage is a quiet "you guys." Alone on the stairs, their voices at
his back — if it's you, you can do this — he whispers an apology and climbs.

**candidate** `p0009_07, p0009_08, p0009_09, p0009_10, p0010_03, p0010_04`

The schoolboy points toward the stage and shouts that the ice statue is moving. The presenter dismisses the claim as incorrect until she hears the sudden sound of fracturing frost. Even as shards tumble from the display, she looks back at the cracking monument. The ice encasing he shatters violently while the guide gasps that this cannot be happening.

### Beat 11

**reference** 

Twenty-five years later, under a clear Seoul sky, a lecture hall is learning
about the monsters humanity never beat. The presenter recounts how the Frost
Queen froze the Pacific with a wave of her hand — and how the Nest Attack
Team, the Five Heroes, went to Antarctica to stop her.

**candidate** `p0010_05, p0010_06, p0010_08, p0011_01, p0011_02`

Jun-Ho bursts violently from the ice, sending frozen shards flying in all directions. The central monument explodes, sending him tumbling heavily toward the hard museum floor. He collapses onto the ground, shivering uncontrollably amid the scattered debris. Breathing the outside air for the first time whispers that he is cold. Then, a dark blue system notification suddenly materializes in the air before him. The glowing text tells him that he has completely absorbed the queen's frozen nucleus.

### Beat 12

**reference** 

On stage stands their memorial: five figures sculpted in ice. Then a boy in
the audience starts shouting — the statue just moved. The presenter laughs it
off, until the cracking starts behind her.

**candidate** `p0011_03, p0011_04, p0011_05, p0011_06, p0012_01, p0012_02, p0012_03`

As the crowd and presenters panic, a modern holographic news window reveals that twenty-five years have passed, which he reads with utter bewilderment from a hospital bed.

### Beat 13

**reference** 

The ice explodes. A young man collapses out of the shards, steaming with
cold, and a system message finally updates: absorption one hundred percent.
Congratulations. The Frost Queen's nucleus is his, and a new skill with it —
Frost, EX rank.

**candidate** `p0012_04, p0012_07, p0012_09, p0012_10, p0012_12, p0012_14`

He watches his hands tremble with strain as he recovers in his hospital bed. The chief doctor, the facility’s medical lead, enters with his staff to say the Player Association president is arriving shortly. He thanks the man while thinking that very few people would actually call him a friend. Visions of his lost comrades flicker as he chuckles.

### Beat 14

**reference** 

His first words in twenty-five years: "Co... cold." As staff rush the stage,
the weakest whisper in the hall belongs to the strongest player alive. The
Frozen Player has returned.

**candidate** `p0013_01, p0013_02, p0013_03, p0013_04, p0013_05, p0013_07`

He approaches the hospital window to survey a horizon filled with soaring modern skyscrapers. While he watches the clouds drift by, he realizes that their ancient struggle finally bought this tranquility.

### Beat 15

**reference** 

The news breaks worldwide: the legend is awake, the Specter who felled the
Frost Queen, back after twenty-five years of cryogenic sleep. The man himself
sits in a hospital bed scrolling headlines, muttering that it's really been
that long. He can barely close his shaking hand into a fist.

**candidate** `p0013_08, p0013_12, p0013_15, p0013_16, p0013_17, p0013_18`

Jun-Ho looks down thoughtfully at his old black mask, holding it in his hands. He hesitates, contemplating his return to a world that remembers him only as a myth. Then, the chief doctor and the nurse enter the room. They stare in profound shock at the sight of his uncovered face. The chief doctor calls him Specter with a trembling voice. He asks why he decided to take off his mask.

### Beat 16

**reference** 

A doctor announces the president of the Player Association is on his way.
Jun-Ho isn't interested in strangers — but this one, they say, is an old
friend. He takes off his mask to the staff's disbelief and waits.

**candidate** `p0014_01, p0014_03, p0014_04, p0014_05, p0014_07, p0014_08`

Jun-Ho smiles at the confused medical team as Deok-gu marches into the room with his bodyguards, the association's security detail. He demands to know what is happening while the chief doctor stammers in surprise. Deok-gu promises to explain everything to him before requesting a private moment so the staff can withdraw.

### Beat 17

**reference** 

The president arrives flanked by suits, and one look is enough. Deok-gu — the
same voice, minus the hair. Jun-Ho bursts out laughing: he called that
M-pattern baldness twenty-five years ago. So much for a touching reunion.

**candidate** `p0014_09, p0014_10, p0014_11, p0015_01, p0015_02, p0015_03`

Deok-gu stands by the hospital bed and says that Jun-Ho looks exactly the same. Recognizing that familiar voice smiles before pointing and laughing at his old friend’s M-pattern baldness. He mutters about their touching reunion while Deok-gu rubs his head. Deok-gu pulls up a chair and admits that his friend has not changed at all.

### Beat 18

**reference** 

Alone, Deok-gu lays out the missing years. When the Frost Queen fell, every
player heard the same message, and the world wept with joy — for about a
minute. Then a dimensional elevator rose in the Pacific: the second floor was
open, ten floors in all. Stay strong until the final floor.

**candidate** `p0015_04, p0015_06, p0015_07, p0015_08, p0016_05, p0016_06`

Turning serious, Deok-gu explains what happened after the Frost Queen fell to Jun-Ho, recounting how the system broadcasted the historic victory to all the players on Earth.

### Beat 19

**reference** 

Jun-Ho does the math out loud — five years for one floor, so in twenty-five
they should be on the seventh. Deok-gu can barely say it: humanity has
cleared one. The third floor is a sea of lava, and the only thing that can
cool it is an altar that demands the Frost Queen's nucleus.

**candidate** `p0016_07, p0016_08, p0016_09, p0016_10, p0016_11, p0016_13, p0016_16`

The jubilant citizens across the globe rejoice and cry tears of joy over the hard-won victory. But he knows the world refuses to let this collective peace last for even a single minute. A sharp chime echoes everywhere as the system announces a dimensional elevator has been installed in the Pacific Ocean. The celebrating spectators freeze, asking what this terrifying new development means as they look upward in absolute horror.

### Beat 20

**reference** 

The nucleus they searched the Nest decades for. Jun-Ho goes very quiet,
because he knows exactly where it is — he absorbed it. With the straightest
face he can manage, he declares they were simply unlucky, and everyone should
be understanding about honest mistakes. Deok-gu is not.

**candidate** `p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04`

Following a massive international summit, an expedition squad was sent to the second floor of the new frontier, which yielded incredible new magic, technology, and resources.

### Beat 21

**reference** 

That evening, Jun-Ho asks where his team ended up. The Seoul History Museum —
though Deok-gu warns the streets below are crawling with reporters. Which is
why, hours later, a hooded figure badges through a service door instead.

**candidate** `p0017_05, p0017_06, p0017_07, p0017_10, p0018_01, p0018_02`

Jun-Ho asks what followed that announcement while resting in his hospital room. Deok-gu explains that the Dimensional Elevator is a mysterious tower containing ten levels. Considering twenty-five years have passed assumes humanity reached the seventh floor. He looks down while comparing this progress to the legacy of Khali, Skaya, and the marksman.

### Beat 22

**reference** 

He walks past a dragon's skeleton — annoyed they put that thing on display —
into a hall kept cold on purpose. There they are: his four friends, frozen
mid-stride, exhibited like trophies.

**candidate** `p0018_03, p0018_04, p0018_06, p0018_09, p0018_12, p0018_13, p0018_14, p0018_16`

Deok-gu remains absolutely silent and refuses to answer. Sweat drips down his face as he stares in growing disbelief. The president covers his mouth, trying to stall for time. Finally, Deok-gu quietly says that humanity has only cleared the second floor. He stares blankly ahead, completely stunned by this slow progress. Then he flops backward onto his hospital bed and covers his face. Ultimately, he tells Deok-gu that he has nothing left to say.

### Beat 23

**reference** 

He sits down in front of them and apologizes for being late. Four paper cups,
one bottle shared with the dead — the world is a better place now, he tells
them; the peace they dreamed of held. So now... rest.

**candidate** `p0019_01, p0019_02, p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12, p0019_13`

Jun-Ho lies on his back with his hands pressed to his forehead, lamenting the twenty-five lost years. He sits up in anger to confront Deok-gu. He demands to know why the players only managed to clear the second floor. Glaring at his sweating friend, he snaps that he is only asking out of sheer curiosity.

### Beat 24

**reference** 

He can't finish the sentence. Brushing the dust from Skaya's ice, he mutters
that the alcohol tastes sweet. Then a system message cuts through the grief:
Frost EX confirmed — insufficient magic — seal removal failed.

**candidate** `p0020_01, p0020_02, p0020_03, p0020_04, p0020_05, p0020_06`

Deok-gu clutches his forehead in frustration and tells Jun-Ho they searched the nest countless times for answers. He looks dejected even as he explains that the cooling nucleus simply vanished from the site. He thinks the failure was inevitable since he already absorbed that power himself.

### Beat 25

**reference** 

Seal. Not tomb. The message spells it out: with the Frost skill, the ice
holding his friends can be undone. They were never dead — and now the
strongest player in history, reduced to a shaking fist, has a reason to start
over. What?!

**candidate** `p0020_07, p0020_08, p0020_10, p0020_11, p0020_12, p0020_14`

Jun-Ho rests a hand on his friend's shoulder to tell Deok-gu they were simply unlucky. He says they should be understanding because mistakes happen in such a desperate era. Deok-gu’s eyes fill with tears while he smiles with serene, quiet warmth. The association president shouts with joy while weeping from a sudden burst of radiant relief.

### Beat 26

**reference** 

(no reference beat)

**candidate** `p0020_15, p0021_01, p0021_12, p0021_13, p0022_01, p0022_02, p0022_03, p0022_04, p0022_05, p0022_06, p0022_07`

Jun-Ho sweats while trying to calculate how much nagging he can endure from his friend. Even as Deok-gu warns him about the reporters swarming below, he slips away toward the museum. He passes security and marvels at a massive dragon skeleton displayed in the hall. Finally, he finds his frozen teammates and apologizes for being so late.

### Beat 27

**reference** 

(no reference beat)

**candidate** `p0023_01, p0023_02, p0023_04, p0023_05, p0023_06, p0023_07`

Jun-Ho pictures his allies together and happy in a fond memory. He tells Skaya that peace is secured. Their shared dream of a safe world has finally become a reality. Looking at Khali he urges them all to rest. Next, he addresses the marksman with a soft farewell. Alcohol splashes from a green bottle into tiny paper cups.

### Beat 28

**reference** 

(no reference beat)

**candidate** `p0023_08, p0023_09, p0023_10, p0023_12, p0023_13, p0024_01, p0024_03`

As his hand taps the ice, a system notification flashes before him. The system confirms his possession of the Frost(EX) skill, which enables him to remove the seal on the ice status. However, his magic stats are insufficient, causing the attempt to fail. He gasps in shock at the sudden revelation.
