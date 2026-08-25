# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `experiments/oneshot-fp-ch1-2/arm_d.md`

## Content (does it tell the same story?)

- fact_coverage: **0.39** of 303 salient reference terms
- order_tau: **0.24** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): answer, 25 years, precise, humanity's, she's, whole, understands, nothing, bro, fool, around, forms, blade, answers, simple, i'll, kill, nightmare, collide, midair, trading, goku, goku's, speed, gathers

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 21 |
| words | 979 | 1126 |
| avg_sentence_words | 11.9 | 13.7 |
| caption_markers_per_100w | 0.0 | 0.18 |
| speech_verbs_per_100w | 1.43 | 1.78 |
| connectives_per_100w | 4.19 | 1.87 |
| max_consecutive_pronoun_starts | 3 | 2 |
| pronoun_start_fraction | 0.2 | 0.22 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** 

# Arm D — current pipeline, gemini-3.5-flash (existing best) A blue status window pops up to let Seo Jun-Ho know he has finally encountered the Frost Queen, the final boss of the Antarctic dungeon. Floating above the ground, she sneers and asks how it feels to get here by abandoning his comrades to die. The Frost Queen sneers, asking Seo Jun-Ho if he actually thinks this is over. Apparently, our frozen monarch thinks he is missing some crucial context.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** 

She tells him that he really is ignorant about this world. Jun-Ho clashes with the Frost Queen. They exchange rapid blows that create bright sparks of energy. The two combatants maneuver through the air, leaving dark and light energy trails in their wake.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** 

The Frost Queen smiles as she begins to dissolve into pure light. Our guy is not here to make friends. Holding his weapon, Jun-Ho looks down coldly and replies that he can't say the same. He strikes her one last time.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** 

Twenty-five years ago in Antarctica, a towering ice pillar stands amidst a swirling blizzard with a blue portal at its base. This is the final dungeon, the Frost Queen's Nest. The team stands in a large hall before a doorway, where Khali, a member of the original five heroes, slumps against the wall in the foreground. Skaya tells Khali to calm down.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** 

A system message appears, declaring that only one person may go up the stairs. The Marksman explains that with the sole exception of Jun-Ho. A sharp click of the tongue cuts through the silence. Khali clenches his jaw in silent frustration.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** 

He is deeply frustrated that he cannot be the one to go. Still, the giant sighs and holds out a hand to yield. Skaya looks forward with a serious expression. She silently reasons that it is best if Specter is the one who goes.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** 

Soon, the four comrades stand together. Jun-Ho stands opposite his four comrades and asks if they are absolutely sure they will not regret their choice. A voice echoes back, questioning the very idea of regret. Before the final battle against the Frost Queen freezes them all in ice, the comrades stand together in a somber moment.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** 

Skaya joins Khali and the Marksman to offer their final encouragement to Jun-Ho. Twenty-five years pass, bringing the story to the present day. Outside a modern facility on a grassy hill, the legacy of the monsters still looms. Inside, the presenter, the event host, tells an audience about the terrifying Frost Queen.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** 

A grand reveal of the five heroes frozen in ice is presented to the audience. / The presenter reveals the frozen statues of the Five Heroes, but as he dismisses a schoolboy's observation, the ice encasing Seo Jun-Ho shatters violently. Jun-Ho shivers intensely as he finally breathes the air outside the ice, his mind screaming at the sudden cold. A dark blue system notification appears in mid-air to announce that he has completely absorbed the Frost Queen's nucleus.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** 

In a hospital bed, Jun-Ho reads the headline: the Specter has returned. He can barely even close his fist. The chief doctor enters, announcing that the Association President is on his way. Jun-Ho quietly reflects that there is not a lot of people who would call him their friend.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** 

He offers a quick word of thanks to the chief doctor, a man, for the heads-up. Deok-gu, the Association President, bursts in with a security detail. He clears the room for a private talk. He looks at his old friend and marvels that Jun-Ho hasn't aged a single day.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** 

Jun-Ho sits up in his hospital bed, pointing and laughing at Deok-gu. Deok-gu looks deeply offended by the sudden teasing. Rubbing his head in sheer frustration, Deok-gu tries to calm down while his newly awakened friend watches him from the bed. In a flashback to the day the Frost Queen fell, Deok-gu, Jun-Ho's old friend and the current President, cries out to him that he finally succeeded.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** 

A global system announcement declares that safe zones will now appear on the area Earth. In the city streets, a jubilant crowd of citizens rejoices, crying tears of joy in absolute relief. But the world is about to change. The Frost Queen was dead, safe zones were popping up, and humanity thought they had actually won.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** 

The victory party lasted about five minutes before a glowing cyan system message ruined the vibe: [A DIMENSIONAL ELEVATOR HAS BEEN INSTALLED IN THE PACIFIC OCEAN.] Just like that, the celebration died. A man, a man, and a woman in a red blazer look up in absolute shock. They cannot believe their eyes. The entire auditorium erupts into a furious uproar as people raise their fists and shout in disbelief.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** 

They demand to know what nonsense this is. Jun-Ho remembers when the public found out about the second floor. People did not take it well. Deok-gu explains that those events created the current structure.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** 

But the frozen player snaps that this is not what Jun-Ho wants to know. His old friend clarifies that there are a total of ten floors in the Dimensional Elevator. Jun-Ho stares down solemnly as the ghostly memories of his frozen comrades Khali, Skaya, and The Marksman weigh heavily behind him. He asks Deok-gu what is currently happening in the world.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** 

Deok-gu merely stares at the ground in silence. Jun-Ho lies flat on his back, pressing his hands against his forehead as he reels from the fact that twenty-five years have passed. Sitting up abruptly, he unleashes a menacing green aura and demands to know if the remaining players truly only cleared the second floor in all that time. Deok-gu looks down somberly as he explains the situation to Jun-Ho.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** 

He says that only a handful of players capable of resisting the extreme heat can even explore the magma. Deok-gu clutches his forehead in deep frustration and tells Jun-Ho that they searched the Nest countless times. He realizes the truth in silence, knowing he absorbed the core himself. Jun-Ho smiles awkwardly and sweats, feeling completely overwhelmed as Deok-gu cries tears of joy.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** 

He silently curses his luck in his head. Later, he sits cross-legged on his hospital bed and reviews a tablet. An interface flashes green as Seo Jun-Ho gets his authentication approved. The system does not care that he is a legend; he still has to scan in like everyone else.

### Beat 20

**reference** 

The skill frost axe can free them from the frozen prison, but his magic stat is too low. Seal removal failed. His stats went back to level one after the hibernation, but every floor of the elevator cleared gives a permanent boost. So, the plan writes itself.

**candidate** 

Jun-Ho pours a drink, telling the statues that the world is finally peaceful. He takes a sip and asks if the alcohol tastes sweet. Then he notices dust on Skaya's face and reaches out to clean it. Jun-Ho recoils in utter shock.

### Beat 21

**reference** 

Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's becoming a player again.

**candidate** 

He has the key to save his old friend, but he lacks the strength to turn it. Talk about a tease.
