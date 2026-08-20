# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.47** of 303 salient reference terms
- order_tau: **0.18** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): 25 years, precise, humanity's, dungeon, monster, she's, feels, make, whole, behind, cuts, fool, forms, blade, pure, simple, i'll, nightmare, midair, trading, goku, goku's, speed, fires, dodges

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 28 |
| words | 979 | 1376 |
| avg_sentence_words | 11.9 | 14.3 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 1.43 | 2.18 |
| connectives_per_100w | 4.19 | 2.83 |
| max_consecutive_pronoun_starts | 3 | 2 |
| pronoun_start_fraction | 0.2 | 0.25 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07, p0002_01, p0002_02, p0002_03, p0002_04, p0002_05, p0002_06`

Seo Jun-Ho, enters the Frost Queen's Nest as the system confirms the icy ruler's presence. Frost Queen, the final boss of the Antarctic gate, mocks him for abandoning his comrades. He snaps that they will not die and tells her to shut it before promising her certain death.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** `p0002_09, p0002_10, p0002_11, p0003_01, p0003_02, p0003_03`

Jun-Ho steps firmly onto the ice, shattering the frozen floor beneath his weight. He lunges into the air to meet the Frost Queen as their powers collide with blinding force. Rapid blows echo through the throne room, leaving dark and light energy trails in their wake. A massive burst of ice suddenly pushes him back.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** `p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

The Frost Queen smiles and gathers a lethal surge of magic in her palm. Jun-Ho gasps as the chamber vanishes in a blinding explosion. He lands in a low crouch, and shards of the floor rain around him. He stands before the defeated ruler in her crystalline throne room.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10, p0005_11, p0005_12, p0005_14, p0006_02, p0006_03, p0006_04`

After Jun-Ho delivers a final strike, ice rapidly grows over him to begin his long hibernation, transitioning back to Antarctica twenty-five years ago where Khali, the tattooed giant of the original five-member hero party, punches an ice wall in frustration.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** `p0006_05, p0006_06, p0006_07, p0006_08, p0006_09, p0007_02, p0007_03`

Skaya, the white-haired healer of the original five-member hero party, and the marksman, the long-range attacker of the original five-member hero party, tell him that he must go alone due to their elemental disadvantages.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** `p0007_04, p0007_05, p0007_06, p0007_07, p0007_08, p0007_09, p0007_10, p0007_11`

Khali concedes his spot to let his friend proceed, and his teammates assure him that they trust him completely, knowing he will not let them die in vain.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** `p0008_02, p0008_03, p0008_04, p0008_05, p0008_06, p0008_07`

Skaya warmly smiles and reminds Jun-Ho that she trusts him to succeed, leaving him to stare forward silently.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** `p0008_08, p0008_09, p0008_10, p0008_11, p0008_12, p0008_13`

Jun-Ho faces his somber teammates during their final moments together. Skaya apologizes to him. Khali tells him that he can succeed. Beside them, the marksman remains silent. Twenty-five years pass in an instant under a clear, bright sky. A modern white building stands on a grassy hill in the present day.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** `p0009_01, p0009_02, p0009_03, p0009_04, p0009_05, p0009_06`

Inside a dark museum auditorium, a schoolboy, a young student, asks the presenter about the Nest Attack Team. The man, a museum guide, replies that the boy is correct and snaps his fingers. Stage lights illuminate Seo Jun-Ho and his frozen teammates as he introduces them as the legendary Five Heroes.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** `p0009_07, p0009_08, p0009_09, p0009_10, p0010_03, p0010_04`

The schoolboy points toward the stage and shouts that the ice statue is moving. The presenter dismisses the claim as incorrect until she hears the sudden sound of fracturing frost. Even as shards tumble from the display, she looks back at the cracking monument. The ice encasing he shatters violently while the guide gasps that this cannot be happening.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** `p0010_05, p0010_06, p0010_08, p0011_01, p0011_02`

Jun-Ho bursts violently from the ice, sending frozen shards flying in all directions. The central monument explodes, sending him tumbling heavily toward the hard museum floor. He collapses onto the ground, shivering uncontrollably amid the scattered debris. Breathing the outside air for the first time whispers that he is cold. Then, a dark blue system notification suddenly materializes in the air before him. The glowing text tells him that he has completely absorbed the queen's frozen nucleus.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** `p0011_03, p0011_04, p0011_05, p0011_06, p0012_01, p0012_02, p0012_03`

As the crowd and presenters panic, a modern holographic news window reveals that twenty-five years have passed, which he reads with utter bewilderment from a hospital bed.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** `p0012_04, p0012_07, p0012_09, p0012_10, p0012_12, p0012_14`

He watches his hands tremble with strain as he recovers in his hospital bed. The chief doctor, the facility’s medical lead, enters with his staff to say the Player Association president is arriving shortly. He thanks the man while thinking that very few people would actually call him a friend. Visions of his lost comrades flicker as he chuckles.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** `p0013_01, p0013_02, p0013_03, p0013_04, p0013_05, p0013_07`

He approaches the hospital window to survey a horizon filled with soaring modern skyscrapers. While he watches the clouds drift by, he realizes that their ancient struggle finally bought this tranquility.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** `p0013_08, p0013_12, p0013_15, p0013_16, p0013_17, p0013_18`

Jun-Ho looks down thoughtfully at his old black mask, holding it in his hands. He hesitates, contemplating his return to a world that remembers him only as a myth. Then, the chief doctor and the nurse enter the room. They stare in profound shock at the sight of his uncovered face. The chief doctor calls him Specter with a trembling voice. He asks why he decided to take off his mask.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** `p0014_01, p0014_03, p0014_04, p0014_05, p0014_07, p0014_08`

Jun-Ho smiles at the confused medical team as Deok-gu marches into the room with his bodyguards, the association's security detail. He demands to know what is happening while the chief doctor stammers in surprise. Deok-gu promises to explain everything to him before requesting a private moment so the staff can withdraw.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** `p0014_09, p0014_10, p0014_11, p0015_01, p0015_02, p0015_03`

Deok-gu stands by the hospital bed and says that Jun-Ho looks exactly the same. Recognizing that familiar voice smiles before pointing and laughing at his old friend’s M-pattern baldness. He mutters about their touching reunion while Deok-gu rubs his head. Deok-gu pulls up a chair and admits that his friend has not changed at all.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** `p0015_04, p0015_06, p0015_07, p0015_08, p0016_05, p0016_06`

Turning serious, Deok-gu explains what happened after the Frost Queen fell to Jun-Ho, recounting how the system broadcasted the historic victory to all the players on Earth.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** `p0016_07, p0016_08, p0016_09, p0016_10, p0016_11, p0016_13, p0016_16`

The jubilant citizens across the globe rejoice and cry tears of joy over the hard-won victory. But he knows the world refuses to let this collective peace last for even a single minute. A sharp chime echoes everywhere as the system announces a dimensional elevator has been installed in the Pacific Ocean. The celebrating spectators freeze, asking what this terrifying new development means as they look upward in absolute horror.

### Beat 20

**reference** 

The skill frost axe can free them from the frozen prison, but his magic stat is too low. Seal removal failed. His stats went back to level one after the hibernation, but every floor of the elevator cleared gives a permanent boost. So, the plan writes itself.

**candidate** `p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04`

Following a massive international summit, an expedition squad was sent to the second floor of the new frontier, which yielded incredible new magic, technology, and resources.

### Beat 21

**reference** 

Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's becoming a player again.

**candidate** `p0017_05, p0017_06, p0017_07, p0017_10, p0018_01, p0018_02`

Jun-Ho asks what followed that announcement while resting in his hospital room. Deok-gu explains that the Dimensional Elevator is a mysterious tower containing ten levels. Considering twenty-five years have passed assumes humanity reached the seventh floor. He looks down while comparing this progress to the legacy of Khali, Skaya, and the marksman.

### Beat 22

**reference** 

(no reference beat)

**candidate** `p0018_03, p0018_04, p0018_06, p0018_09, p0018_12, p0018_13, p0018_14, p0018_16`

Deok-gu remains absolutely silent and refuses to answer. Sweat drips down his face as he stares in growing disbelief. The president covers his mouth, trying to stall for time. Finally, Deok-gu quietly says that humanity has only cleared the second floor. He stares blankly ahead, completely stunned by this slow progress. Then he flops backward onto his hospital bed and covers his face. Ultimately, he tells Deok-gu that he has nothing left to say.

### Beat 23

**reference** 

(no reference beat)

**candidate** `p0019_01, p0019_02, p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12, p0019_13`

Jun-Ho lies on his back with his hands pressed to his forehead, lamenting the twenty-five lost years. He sits up in anger to confront Deok-gu. He demands to know why the players only managed to clear the second floor. Glaring at his sweating friend, he snaps that he is only asking out of sheer curiosity.

### Beat 24

**reference** 

(no reference beat)

**candidate** `p0020_01, p0020_02, p0020_03, p0020_04, p0020_05, p0020_06`

Deok-gu clutches his forehead in frustration and tells Jun-Ho they searched the nest countless times for answers. He looks dejected even as he explains that the cooling nucleus simply vanished from the site. He thinks the failure was inevitable since he already absorbed that power himself.

### Beat 25

**reference** 

(no reference beat)

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
