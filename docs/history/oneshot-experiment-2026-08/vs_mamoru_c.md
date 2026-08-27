# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `experiments/oneshot-fp-ch1-2/arm_c.md`

## Content (does it tell the same story?)

- fact_coverage: **0.47** of 303 salient reference terms
- order_tau: **0.37** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): answer, 25 years, precise, humanity's, dungeon, monster, snap, she's, leaving, behind, understands, nothing, bro, cuts, fool, around, answers, i'll, collide, midair, trading, blows, goku, goku's, speed

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 37 |
| words | 979 | 1002 |
| avg_sentence_words | 11.9 | 6.8 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 1.43 | 3.19 |
| connectives_per_100w | 4.19 | 1.5 |
| max_consecutive_pronoun_starts | 3 | 4 ⚠ |
| pronoun_start_fraction | 0.2 | 0.51 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** 

# One-shot freeform write — gemini-3.5-flash <!-- project: projects/return-of-the-frozen-player-ch1-2 | temp: 0.9 | tokens: 26650 in / 1264 out --> The frozen throne looms in the absolute cold. Seo Jun-Ho stands before the queen of ice. She mocks his sacrifice. She asks how it feels to abandon his comrades.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** 

He draws his blade. He tells her that his allies do not die easily. He vows to end this nightmare. Their weapons clash with a deafening ring.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** 

The impact shakes the cavern. He slides backward. The queen of ice summons her frost. He charges once more.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** 

The fate of humanity rests on his blade. He attacks with everything he has. The duel is brief but brutal. Jun-Ho pierces her chest.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** 

She laughs. She says that it was fun. Her body shatters into glittering light. A blue system message appears.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** 

It declares that he is absorbing the Frost Queen's power. His hands begin to freeze. He tries to move. He cannot.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** 

Another system message warns him. His body will hibernate. He must fully absorb the Frost Queen's nucleus. He turns to solid ice.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** 

The darkness swallows him whole. Seventy-six hours earlier, the Nest Attack Team stood outside. They reached the final gate of the Frost Queen's Nest. A system message blocked their path.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** 

It stated that only one person could ascend the stairs. Khali was furious. He demanded to know if this was a suicide mission. Skaya calmed the tattooed giant down.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** 

She argued that they had very little time left. She suggested that Specter should go alone. The marksman agreed. He pointed out that they were at a disadvantage against ice.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** 

Khali conceded. The swordswoman also trusted him. They sent Jun-Ho forward. They believed he would return.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** 

Twenty-five years pass in an instant. It is now 2024. In a museum, a guide explains the history of the Five Heroes. She praises the legendary players.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** 

She tells the audience that they made the greatest achievement in history. She says they defeated the Frost Queen. A child suddenly interrupts her. He screams that the ice statue is moving.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** 

The guide tries to reassure the crowd. She says the temperature is strictly controlled. She warns them not to touch the glass. But the ice cracks loudly.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** 

Jun-Ho bursts free from his frozen shell. He falls forward. The crowd panics. People run.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** 

A system message congratulates him. It states his absorption rate is one hundred percent. He has completely absorbed the Frost Queen's nucleus. He receives a new skill.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** 

It is Frost (EX). He collapses to the floor. It is cold. Later, he wakes up in a hospital bed.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** 

Holographic news screens float in the air. The headlines declare the return of the legendary Specter. He stares at his hands. He realizes he has slept for twenty-five years.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** 

He complains that his body feels incredibly weak. He can barely clench his fist. He sighs. A nurse enters the room.

### Beat 20

**reference** 

The skill frost axe can free them from the frozen prison, but his magic stat is too low. Seal removal failed. His stats went back to level one after the hibernation, but every floor of the elevator cleared gives a permanent boost. So, the plan writes itself.

**candidate** 

She informs him that the Player Association president is arriving. Jun-Ho wonders if it is someone he knows. He dislikes being bothered. He tells her that he will send any strangers away.

### Beat 21

**reference** 

Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's becoming a player again.

**candidate** 

The door opens. A large bald man enters with a security detail. Jun-Ho smiles. He recognizes the bald association president as his old friend, Deok-gu.

### Beat 22

**reference** 

(no reference beat)

**candidate** 

Deok-gu orders his guards to leave the room. He looks at Jun-Ho with tears in his eyes. He says that his old friend looks exactly the same. Jun-Ho laughs.

### Beat 23

**reference** 

(no reference beat)

**candidate** 

He teases Deok-gu about his baldness. He asks why they have not cured hair loss in twenty-five years. Deok-gu sighs. He says that some things never change.

### Beat 24

**reference** 

(no reference beat)

**candidate** 

Jun-Ho asks why the doctors were so shocked by his awakening. He believes the world is finally at peace. Deok-gu looks down. He explains that things are not so simple.

### Beat 25

**reference** 

(no reference beat)

**candidate** 

He recounts the events of their victory. The moment the Nest was cleared, a global system message appeared. It announced the installation of a dimensional elevator in the Pacific Ocean. The tower contains ten floors.

### Beat 26

**reference** 

(no reference beat)

**candidate** 

Humanity rejoiced at first. But the joy did not last. Jun-Ho asks what floor they are currently on. He expects they have reached the seventh floor.

### Beat 27

**reference** 

(no reference beat)

**candidate** 

Deok-gu remains silent. He looks away in shame. He confesses that they are only on the second floor. Jun-Ho is stunned.

### Beat 28

**reference** 

(no reference beat)

**candidate** 

He asks why they have made so little progress. Deok-gu explains the problem. He says the third floor is a volcanic region of pure lava. The players found an altar in the magma.

### Beat 29

**reference** 

(no reference beat)

**candidate** 

A system message revealed that they need the Frost Queen's nucleus to cool the environment. Deok-gu explains that they searched the Nest countless times. They could never find the core. Jun-Ho breaks into a cold sweat.

### Beat 30

**reference** 

(no reference beat)

**candidate** 

He realizes he absorbed the core. He decides to keep this a secret. He comforts his friend. He says that everyone makes mistakes.

### Beat 31

**reference** 

(no reference beat)

**candidate** 

Deok-gu is deeply moved. Jun-Ho asks about his old comrades. Deok-gu warns him that the museum is surrounded by reporters. He advises Jun-Ho to slip out through the side entrance.

### Beat 32

**reference** 

(no reference beat)

**candidate** 

Jun-Ho nods. He promises to return quickly. That night, Jun-Ho sneaks into the Seoul History Museum. He walks past giant skeletal displays.

### Beat 33

**reference** 

(no reference beat)

**candidate** 

He finds the exhibition of his frozen comrades. The statues of Skaya, Khali, and the unnamed heroes stand frozen in blocks of ice. Jun-Ho sits before them. He pours cups of alcohol.

### Beat 34

**reference** 

(no reference beat)

**candidate** 

He tells them that the world is a better place now. He drinks to their memory. He whispers that they protected the peace they dreamed of. He notices they are covered in dust.

### Beat 35

**reference** 

(no reference beat)

**candidate** 

He reaches out to wipe Skaya's face. Suddenly, a blue system message pops up. It confirms he possesses the Frost (EX) skill. A second message appears.

### Beat 36

**reference** 

(no reference beat)

**candidate** 

It states his magic stats are insufficient. The system declares he has failed to remove the seal. He is stunned. But a final message flashes.

### Beat 37

**reference** 

(no reference beat)

**candidate** 

It reveals that with his frost skill, he can remove the seal on the ice statues. He realizes they are not dead. He can save his friends. He just needs to grow stronger.
