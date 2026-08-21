# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.35** of 303 salient reference terms
- order_tau: **0.2** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): 25 years, precise, she's, feels, make, whole, behind, understands, fool, forms, giant, blade, pure, simple, i'll, nightmare, collide, midair, trading, goku, goku's, speed, fires, blank, dodges

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 28 |
| words | 979 | 818 |
| avg_sentence_words | 11.9 | 14.6 |
| caption_markers_per_100w | 0.0 | 0.12 |
| speech_verbs_per_100w | 1.43 | 3.42 |
| connectives_per_100w | 4.19 | 2.69 |
| max_consecutive_pronoun_starts | 3 | 2 |
| pronoun_start_fraction | 0.2 | 0.25 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07`

Seo Jun-Ho, a legendary hero known as Specter stands in the frozen throne room of the Frost Queen's Nest. The system announces his encounter with the Frost Queen, the boss of the final Antarctic dungeon. She mocks him for abandoning his comrades, but he replies they will not croak easily.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** `p0002_01, p0002_02, p0002_03, p0002_04, p0002_05, p0002_06`

The Frost Queen laughs and asks if he truly believes the battle is over. Even as she mocks his ignorance and readies an ice sword, Jun-Ho tells her to shut it. He has no time for games and gathers dark energy to end her life.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** `p0002_09, p0002_10, p0002_11, p0003_01, p0003_02, p0003_03`

Jun-Ho plants his boot against the slick floor, shattering the frost with every heavy step. He leaps into a frantic mid-air duel, meeting the Frost Queen blow for blow. Their energy-charged strikes fill the throne room with blinding sparks and violent motion. Just as he presses forward, a sudden burst of ice magic throws him back.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** `p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

The Frost Queen smiles while gathering a lethal surge of energy in her palm. Jun-Ho mutters in shock before a blinding explosion tears through the throne room. Ice shards swirl as the floor shatters from the impact of his heavy landing. Finally, he stands victorious over his fallen foe within the ruins of her palace.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10, p0005_11`

Dissolving into light, the Frost Queen smiles and admits the duel was fun. Jun-Ho stares her down, coldly replying he cannot say the same. A final strike triggers an explosion, yet sudden frost anchors to his skin. He shouts in shock as the system triggers a hibernation to absorb her nucleus, a concentrated core of power.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** `p0005_12, p0005_14, p0006_02, p0006_03, p0006_04, p0006_05, p0006_06, p0006_07, p0006_08, p0006_09`

Khali, a member of the original five heroes, rages. Still, the team says Jun-Ho must enter the final gate alone.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** `p0007_02, p0007_03, p0007_04, p0007_05, p0007_06, p0007_07`

Although frustrated by his own elemental limits, Khali yields, and Skaya agrees that only Specter has what it takes to climb the stairs.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** `p0007_08, p0007_09, p0007_10, p0007_11, p0008_02, p0008_03`

He asks his allies if they will regret their choice. The Marksman replies that they trust him.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** `p0008_04, p0008_05, p0008_06, p0008_07, p0008_08, p0008_09`

Skaya tells Jun-Ho he must succeed and apologizes for leaving him.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** `p0008_10, p0008_11, p0008_12, p0008_13, p0009_01, p0009_02`

Twenty-five years pass under a clear blue sky, and a modern building now stands on a grassy hill. Inside, the presenter tells a gathered audience about a logic-defying monster that once froze the entire ocean.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** `p0009_03, p0009_04, p0009_05, p0009_06, p0009_07, p0009_08, p0009_09, p0009_10`

The dismissing a schoolboy's claim just as ice cracks around him.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** `p0010_03, p0010_04, p0010_05, p0010_06, p0010_08, p0011_01, p0011_02, p0011_03, p0011_04, p0011_05, p0011_06`

Shards fly as the ice monument explodes and the presenter shouts that there is no way. Jun-Ho crashes onto the floor while muttering that it is cold. The system awards him the Frost skill of the EX-tier, a unique rank of extraordinary power. The security chief, a woman with a dark bob haircut, panics while they ask what is happening.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** `p0012_01, p0012_02, p0012_03, p0012_04, p0012_07, p0012_09`

A weakened Jun-Ho learns twenty-five years have passed. The chief doctor says Deok-gu, his old friend and current President, is coming.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** `p0012_10, p0012_12, p0012_14, p0013_01, p0013_02, p0013_03`

Jun-Ho thanks the chief doctor, his thoughts turning to Skaya.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** `p0013_04, p0013_05, p0013_07, p0013_08, p0013_12, p0013_15`

He remembers that his allies wanted peace, so he lifts his mask to secure their dream.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** `p0013_16, p0013_17, p0013_18, p0014_01, p0014_03, p0014_04`

As the medical staff gasps in awe at his unmasked face, Jun-Ho smiles broadly just as Deok-gu enters the hospital room.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** `p0014_05, p0014_07, p0014_08, p0014_09, p0014_10, p0014_11`

Jun-Ho smiles, recognizing Deok-gu, his old friend and the current President, who dismisses the medical staff.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** `p0015_01, p0015_02, p0015_03, p0015_04, p0015_06, p0015_07`

Pointing from his bed, Jun-Ho laughs at the receding hairline of Deok-gu, his old friend and the current President. His offended friend snaps back, asking if baldness is the first thing he has to say.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** `p0015_08, p0016_05, p0016_06, p0016_07, p0016_08, p0016_09, p0016_10, p0016_11, p0016_13, p0016_16`

Deok-gu recounts how global celebration of the Frost Queen's defeat was cut short when a Dimensional Elevator appeared in the Pacific Ocean.

### Beat 20

**reference** 

The skill frost axe can free them from the frozen prison, but his magic stat is too low. Seal removal failed. His stats went back to level one after the hibernation, but every floor of the elevator cleared gives a permanent boost. So, the plan writes itself.

**candidate** `p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04`

He says world leaders sent an expedition to the newly unlocked second floor for its vast resources.

### Beat 21

**reference** 

Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's becoming a player again.

**candidate** `p0017_05, p0017_06, p0017_07, p0017_10, p0018_01, p0018_02`

Deok-gu says the elevator has ten floors, leaving Jun-Ho to lament humanity's slow progress.

### Beat 22

**reference** 

(no reference beat)

**candidate** `p0018_03, p0018_04, p0018_06, p0018_09, p0018_12, p0018_13, p0018_14, p0018_16`

Jun-Ho asks if they are still on the first floor, but his companion remains completely silent. Deok-gu merely covers his mouth as sweat beads on his face. When urged for an actual answer, Deok-gu finally replies that they are indeed still on that floor. Stunned by this reality, he flops backward onto his hospital bed and says he has nothing to say.

### Beat 23

**reference** 

(no reference beat)

**candidate** `p0019_01, p0019_02, p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12, p0019_13`

Jun-Ho angrily asks why humanity only cleared the second floor, and Deok-gu explains they are stuck on the volcanic third floor.

### Beat 24

**reference** 

(no reference beat)

**candidate** `p0020_01, p0020_02, p0020_03, p0020_04, p0020_05, p0020_06`

Deok-gu says they searched the Nest, but Jun-Ho knows it was futile because he absorbed it.

### Beat 25

**reference** 

(no reference beat)

**candidate** `p0020_07, p0020_08, p0020_10, p0020_11, p0020_12, p0020_14`

Jun-Ho tells Deok-gu, his old friend and the current President, they were unlucky, but he loudly disagrees.

### Beat 26

**reference** 

(no reference beat)

**candidate** `p0020_15, p0021_01, p0021_12, p0021_13, p0022_01, p0022_02, p0022_03, p0022_04, p0022_05, p0022_06, p0022_07`

He slips away to the secure museum vault. He sits before his frozen comrades and apologizes for keeping them waiting.

### Beat 27

**reference** 

(no reference beat)

**candidate** `p0023_01, p0023_02, p0023_04, p0023_05, p0023_06, p0023_07`

He tells his frozen comrades to rest in peace. He pours alcohol into cups to drink with them.

### Beat 28

**reference** 

(no reference beat)

**candidate** `p0023_08, p0023_09, p0023_10, p0023_12, p0023_13, p0024_01, p0024_03`

After returning to a world stuck on a volcanic floor, Jun-Ho asks his frozen comrades if the alcohol tastes sweet. He mutters a curse while noticing Skaya is covered in dust. When he touches her, the system warns that he must level up his magic stats quickly enough to break their icy seals.
