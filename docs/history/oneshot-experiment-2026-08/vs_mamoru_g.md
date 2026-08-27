# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `experiments/oneshot-fp-ch1-2/arm_g_readable_pages.md`

## Content (does it tell the same story?)

- fact_coverage: **0.56** of 303 salient reference terms
- order_tau: **0.45** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): answer, 25 years, precise, humanity's, snap, she's, laughing, feels, whole, behind, bro, saying, giant, answers, simple, i'll, collide, midair, trading, blows, goku, goku's, speed, gathers, fires

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 22 |
| words | 979 | 1323 |
| avg_sentence_words | 11.9 | 15.0 |
| caption_markers_per_100w | 0.0 | 0.08 |
| speech_verbs_per_100w | 1.43 | 1.36 |
| connectives_per_100w | 4.19 | 1.81 |
| max_consecutive_pronoun_starts | 3 | 2 |
| pronoun_start_fraction | 0.2 | 0.26 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** 

The queen of ice stands tall in her frozen throne room, a crowned monster in an ice gown. She tilts her head, mocking the masked swordsman in the black coat for abandoning his comrades to die just to reach her. Seo Jun-Ho doesn't flinch. He warns her that his team doesn't croak that easily.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** 

He draws his blade as dark energy rolls off his shoulders like smoke. He tells her to shut up, declaring he has no time to fool around. This nightmare ends today. The clash of black energy and jagged ice shatters the throne room.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** 

Jun-Ho slices clean through her desperate defenses, ending the final boss in a brilliant, blinding flash. The Frost Queen crumbles into nothing. Jun-Ho expects the sweet relief of victory, but instead, jagged frost creeps up his own arm. A system message chimes in the silence, announcing that he is actively absorbing the Frost Queen's power.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** 

It brutally warns that his body will go into forced hibernation until he fully absorbs the nucleus. Ice rapidly encases his skin, freezing him solid as the dark dungeon goes entirely quiet. Seventy-six hours earlier, the Nest Attack Team stands at the base of the final stairs in Antarctica. A glowing system prompt blocks their path, declaring that only one person may go up the dimensional elevator to face the boss.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** 

Khali punches the ice wall. The big man in the black tank top is furious, screaming that this is just asking the rest of them to die after coming all this way. Skaya calmly tells Khali to calm down. The white-haired healer reminds them time is short.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** 

She suggests that Specter should be the one to go. The cowboy-hat marksman tips his brim, agreeing entirely. He points out that, with the sole exception of Specter, everyone else is at a massive disadvantage against ice-based abilities. Khali clicks his tongue loudly but concedes the point.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** 

The black-bob swordswoman adds her vote too, stating it is obviously best if Specter goes. The team looks at Jun-Ho with complete, unwavering faith. They warn him that if he loses, they all die a meaningless death, but they trust him to make it count. Jun-Ho turns toward the stairs, apologising softly under his breath as he carries the heavy weight of their sacrifice into the dark.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** 

Twenty-five years later, the world has dramatically moved on. The Five Heroes are now literally museum exhibits, put on display for school children. Inside a temperature-controlled reinforced glass wall, the glacier encasing Specter begins to violently crack. A tour guide dismisses a kid's warning just as a system message chimes in the dark.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** 

It confirms the absorption rate has finally reached one hundred percent. The ice shatters completely in an explosive shockwave, dumping a very confused Jun-Ho onto the polished floor. A prompt reading '[CONGRATULATIONS.]' informs him that he has completely absorbed the core and received the EX-rank frost skill. He stumbles out into a modern auditorium, leaving the museum staff screaming in sheer panic.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** 

Jun-Ho wakes up in a sterile hospital bed, staring blankly at digital news feeds floating in the air. Headlines scream about the legendary return of the greatest player from a twenty-five-year cryogenic slumber. His hands are still shaking violently from the phantom cold, and he marvels that he can barely clench his fists. A nurse warns him that the Player Association president is on his way up right now.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** 

Jun-Ho asks if it is someone he actually knows, grumbling that he hates being bothered and will absolutely send them away if they are a stranger. The nurse assures him the president claims to be his close friend. Jun-Ho considers this, then pulls off his iconic mask. He figures a peaceful world has no need for masked heroes anymore, which basically means he is now unemployed.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** 

The door opens, revealing a heavily guarded, middle-aged man in a sharp suit. Jun-Ho stares at the bald association president, instantly recognising Deok-gu. Jun-Ho ruthlessly mocks his old friend, loudly asking if he didn't predict this exact male-pattern baldness decades ago. Deok-gu sighs heavily, deeply disappointed that he expected a touching reunion from a bastard like Jun-Ho.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** 

The banter flows easily, completely unchanged despite the massive time gap. But Jun-Ho notices the underlying tension in the room. He asks why the medical staff looked so terrified earlier, pointing out that the monster threat should be entirely over. Deok-gu looks grim.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** 

He explains that twenty-five years ago, the exact moment Jun-Ho cleared the final dungeon, every player on Earth received a system message reading '[CONGRATULATIONS.]'. Safe zones appeared across the globe, and humanity wept tears of pure joy. But the world did not let that celebration last a single minute. Another prompt announced that a dimensional elevator had been installed in the Pacific Ocean, opening access to the second floor and declaring, '[MOVING TO THE FRONTIER AREA IS NOW POSSIBLE.]' The world collectively realised the Frost Queen was never the end of the game.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** 

The politicians and associations panicked, eventually sending a massive expedition squad into the frontier. Deok-gu explains that the second floor was a wild land of magic and technology, which ultimately created the affluent modern Earth Jun-Ho sees outside his window. Jun-Ho cuts him off. He demands to know the total number of floors in this tower.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** 

Deok-gu admits there are ten floors in the elevator. Jun-Ho calculates the math in his head. If it took his elite squad five brutal years to clear the first floor, humanity should realistically be pushing the seventh floor by now. He asks Deok-gu what floor they are currently exploring.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** 

The president goes dead silent, sweating profusely under Jun-Ho's intense glare. Deok-gu finally whispers that in twenty-five long years, humanity has only cleared up to the second floor. Jun-Ho nearly has an aneurysm, grabbing his head in disbelief. He is absolutely livid that a quarter of a century has passed and they are stuck at the lobby.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** 

He demands an explanation, promising to hear Deok-gu out just to see how incredibly stupid the excuse is. Deok-gu explains that the third floor is a volatile volcanic region. To progress, players have to find an altar in the middle of a literal lava sea and cool it down. The only item capable of chilling that extreme environment is the Frost Queen's nucleus.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** 

Deok-gu rubs his face in deep shame, admitting they searched the Nest countless times but never found the core in the end. Jun-Ho freezes entirely. He remembers the system message from his victory. He realises he literally absorbed the nucleus into his own body while he slept.

### Beat 20

**reference** 

The skill frost axe can free them from the frozen prison, but his magic stat is too low. Seal removal failed. His stats went back to level one after the hibernation, but every floor of the elevator cleared gives a permanent boost. So, the plan writes itself.

**candidate** 

In a masterclass of rapid backpedalling, Jun-Ho suddenly places a very comforting hand on Deok-gu's shoulder. He warmly tells his old friend that everyone makes mistakes and they should be deeply understanding of each other's failures, which is probably smart when you are the secret reason humanity has been stalled for two decades. Later that night, Jun-Ho sneaks out of the hospital, effortlessly slipping past the media circus swarming the front doors. He heads straight to the Seoul History Museum, receiving an '[AUTHENTICATION SUCCESSFUL.]' prompt and walking through the quiet halls until he finds the grand exhibit room.

### Beat 21

**reference** 

Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's becoming a player again.

**candidate** 

His four comrades stand frozen on grand pedestals, trapped in the exact same ice that held him. Jun-Ho sits on the cold floor before them, pouring out shots of cheap soju. He drinks alone with his frozen friends, telling them they successfully protected the peace they dreamed of and that they can finally rest. He reaches up, gently wiping accumulated dust off Skaya's frozen face.

### Beat 22

**reference** 

(no reference beat)

**candidate** 

A system message pops up, confirming his possession of the EX-rank frost skill. It immediately warns that his magic stats are insufficient and that he has failed to remove the seal. Jun-Ho is shocked, but a second prompt flips the script entirely. It declares that with his new skill, he is actually able to remove the seal on the ice status.
