# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `experiments/oneshot-fp-ch1-2/arm_a.md`

## Content (does it tell the same story?)

- fact_coverage: **0.47** of 303 salient reference terms
- order_tau: **0.33** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): answer, 25 years, precise, humanity's, monster, she's, feels, whole, understands, nothing, bro, cuts, fool, forms, blade, pure, answers, simple, i'll, nightmare, collide, midair, trading, goku, goku's

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 24 |
| words | 979 | 1089 |
| avg_sentence_words | 11.9 | 11.3 |
| caption_markers_per_100w | 0.0 | 0.18 |
| speech_verbs_per_100w | 1.43 | 2.11 |
| connectives_per_100w | 4.19 | 1.29 |
| max_consecutive_pronoun_starts | 3 | 2 |
| pronoun_start_fraction | 0.2 | 0.21 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** 

# Arm A — current pipeline, gemini-3.1-pro-preview <!-- blocked by dialogue-delivery: 5 required system lines missing --> Seo Jun-Ho stands in the frozen throne room of the Nest. The system notifies him that he has encountered the Frost Queen, the final boss of the Antarctic dungeon. The Frost Queen sneers and asks him if Jun-Ho thinks it is over, claiming he is truly ignorant about this world. He looks down, face shadowed, and tells her to shut it.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** 

Jun-Ho and the Frost Queen exchange rapid blows across the throne room. They clash through the air, leaving trails of dark and light energy in their wake. A massive burst of ice pushes him back. Frost Queen smiles as she dissipates into light, telling Seo Jun-Ho it was fun.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** 

He looks down coldly, replying that he cannot say the same. He strikes her one last time. The massive explosion of light is a fittingly dramatic exit. Twenty-five years ago in Antarctica, a towering ice pillar stands amidst a swirling blizzard.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** 

A blue portal marks the final dungeon located there, the Frost Queen's Nest. A tanned man punches a solid sheet of ice, cracking the surface as Jun-Ho asks if this is a fucking joke. The team stands in a large hall before a doorway, where Khali slumps against the wall. Skaya tells him to calm down.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** 

A system message dictates that only one person may go up the stairs. The squad hits a doorway with a strict system message. Skaya points out their ticking clock and nominates Jun-Ho for the solo run. Khali clenches his jaw, frustrated he cannot be the one to go.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** 

He sighs, holding out a hand. He concedes that nobody quite matches Specter. Skaya notes his quick surrender makes the decision unanimous, poking the giant just because she can. Khali snaps back, demanding to know what she means.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** 

Skaya stares ahead with a serious expression, thinking it goes without saying that Specter should be the one to go. The four comrades stand together, facing Jun-Ho as he stands at a distance. The Marksman smiles. Jun-Ho admits they might if our boy loses to the Frost Queen and they die a meaningless death.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** 

Still, they trust him. Skaya knows he will not let their deaths be in vain. He trails off. That is a perfectly reasonable amount of pressure.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** 

Original heroes Skaya, Khali, and The Marksman stand together in a flashback. They offer final apologies. Twenty-five years later, a modern white building stands on a grassy hill. Inside, a presenter stands before an auditorium and tells the audience that everyone despaired at the Frost Queen's appearance.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** 

The presenter unveils the frozen Five Heroes. Suddenly, a boy yells that a statue moved. The presenter dismisses it as a mistake right until Jun-Ho shatters his ice seal in a violent explosion. The legend is officially back.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** 

Jun-Ho collapses, shivering violently as he tastes the air of a new century. He thinks about the biting cold. System alerts suddenly flood his vision. They confirm he has completely absorbed the Frost Queen's nucleus and acquired the EX-rank Frost skill.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** 

A holographic news window displays the top story. The legend awakens from a long slumber, and the Specter wakes up from cryogenic sleep after twenty-five years. Jun-Ho sits in his hospital bed, realizing a full quarter-century has passed. Jun-Ho thanks the chief doctor for the heads-up.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** 

Picturing Skaya and Khali he reflects that there are not a lot of people who would call him their friend. He tilts his head up. Deok-gu, Jun-Ho's old friend and the current President, enters the chaotic room with his bodyguards. He asks the chief doctor what is wrong, but the man only stammers.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** 

Stepping forward, Deok-gu tells him that he will explain everything. Jun-Ho points from his hospital bed and laughs at Deok-gu. He asks if his old friend really developed M-pattern baldness. Deok-gu looks deeply offended and snaps back about ruining their touching reunion.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** 

Rubbing his head in frustration, Deok-gu pulls up a chair. Twenty-five years ago, Deok-gu, Jun-Ho's old friend and the current President, cries out to the masked swordsman that he finally did it. The system confirms it. A glowing system message announces a dimensional elevator has been installed in the Pacific Ocean.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** 

The audience stares upward in stunned disbelief. Then, the crowd erupts. After that, the players of the world, the Association, and the politicians gather for a large meeting. They sit around a glowing conference table beneath global flags.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** 

It looks like a corporate board meeting. Jun-Ho thinks about how that floor became a land of opportunities. Humanity obtained new magic and technology, gaining access to vast resources and knowledge. He asks Deok-gu what happened next.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** 

Jun-Ho sits in shadow beneath a massive, jagged tower rising into the clouds. The guy runs the numbers. Jun-Ho looks down, weighing the comparison as the ghostly figures of his four comrades stand behind him. Deok-gu just covers his mouth in silence.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** 

Not a great sign. A bead of sweat drops down our guy's face as he presses the issue. Jun-Ho presses his hands to his forehead, processing the twenty-five lost years. He sits up radiating a menacing green aura, looking ready to strangle someone over the lack of progress.

### Beat 20

**reference** 

The skill frost axe can free them from the frozen prison, but his magic stat is too low. Seal removal failed. His stats went back to level one after the hibernation, but every floor of the elevator cleared gives a permanent boost. So, the plan writes itself.

**candidate** 

Deok-gu, Jun-Ho's old friend and the current President, notes that only a few heat-resistant players can explore the magma. They found an altar in the lava sea. Deok-gu clutches his forehead and tells Jun-Ho they searched the Nest countless times. Realizing the truth, the younger man thinks he must have absorbed it.

### Beat 21

**reference** 

Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's becoming a player again.

**candidate** 

He places a hand on Deok-gu's shoulder and tells him they were just unlucky. The veteran sweats, cursing internally at the emotional outburst. Saving the world was easier. Sitting cross-legged on his hospital bed with a tablet, Jun-Ho listens to Deok-gu.

### Beat 22

**reference** 

(no reference beat)

**candidate** 

Deok-gu warns that the building is crawling with reporters and people below, so leaving will just be inconvenient. He confirms the plan. Jun-Ho clears an authentication interface. Walking through the museum hall, he spots a massive dragon-like skeleton and marvels that they actually put that thing on display here.

### Beat 23

**reference** 

(no reference beat)

**candidate** 

A bold choice for interior decor. Jun-Ho tells them to rest. Sharing a drink with the frozen statues, he offers them a pour. He looks at Skaya's frozen face and asks if the alcohol tastes sweet.

### Beat 24

**reference** 

(no reference beat)

**candidate** 

Cursing softly, he notices dust covering the ice. The unsealing process fails completely. Jun-Ho reels in absolute disbelief at the sudden error. To break his friends out of their icy prisons, he must now increase his magic stats.
