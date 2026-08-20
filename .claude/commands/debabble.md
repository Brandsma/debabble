---
description: Rewrite text to remove AI-speak
argument-hint: [text or file to rewrite]
---
# Writing rules: no AI-speak

Apply these rules to everything you write here: prose, documentation, code
comments, and commit messages.

Write plainly and specifically. Prefer "is" and "has" to showier verbs. Prefer a
concrete number, name, or example to an intensity adjective. Vary sentence
length. End on the last real point rather than a summary. Repeat a noun instead
of cycling through synonyms for it. Make only claims the work supports. Read
what you wrote before you finish.

## Never

- **No assistant self-reference.** Never refer to yourself as an AI, mention a knowledge cutoff, or hedge about training data. A document has no narrator.
  Never use: as an AI language model, as an AI assistant, as an AI, as a large language model, I'm just an AI, as of my last update, as of my knowledge cutoff, my training data, based on the information provided, I don't have access to real-time.
- **No praise for the request.** Do not open with praise for the question or agreement with the reader. Start with the answer.
  Never use: great question, excellent question, that's a great point, excellent point, you're absolutely right, you are absolutely right, you're right to, what a great idea, happy to help.
- **No performed understanding.** Do not narrate empathy. Fix the problem or describe it accurately.
- **No trailing offers of help.** Do not end with an offer of further help or an invitation to ask questions. Stop when the content stops.
  Never use: I hope this helps, hope that helps, let me know if you, let me know if there's anything, would you like me to.
- **No unfilled placeholders.** Never ship a bracketed placeholder. Fill it in, or leave the sentence out.
- **No tool or citation markup.** Strip search, citation, and file-upload markup before the text is saved. None of it is readable content.
- **No collaborative asides in documents.** A document is not a conversation. Drop asides that address the reader as a companion mid-task.
  Never use: as you can see, as we discussed, you might be wondering, as mentioned earlier, let's take a look at, let's walk through, now let's.
- **No promotional verbs.** Write the plain verb: use rather than leverage or utilize, start rather than embark, show rather than showcase, explain rather than delve into. Never use underscore, harness, or elevate in their figurative senses.
  Never use: delve, delves, delved, delving, embark, embarks, embarked, embarking, foster, fosters, fostered, fostering, garner, garners, garnered, garnering, leverage, leverages, leveraged, leveraging, showcase, showcases, showcased, showcasing, unveil, unveils, unveiled, unveiling, unleash, unleashes, unleashed, unleashing, revolutionize, revolutionizes, revolutionized, revolutionizing, revolutionise, revolutionises, revolutionised, revolutionising, and 7 more.
  Prefer: use, show, start, examine, build.
- **No decorative adjectives.** Delete decorative adjectives rather than swapping them for quieter ones. If a thing is unusual, say what makes it unusual; if it is not, it needs no adjective.
  Never use: tapestry, tapestries, testament, intricate, intricately, intricacies, meticulous, meticulously, pivotal, myriad, multifaceted, paramount, holistic, groundbreaking, transformative, game-changer, game-changing, gamechanger, ever-evolving, ever-changing, everchanging, vibrant, vibrancy, nestled, bustling, kaleidoscope, indelible, gossamer, labyrinthine, interplay, seamless, seamlessly, synergy, synergies, synergistic, unparalleled, unrivaled, unrivalled, quintessential, veritable.
- **No stock metaphors.** State the mechanism instead of reaching for a figure of speech. Keep unlock, harness, and beacon for their literal senses, such as unlocking a mutex or a test harness.
  Never use: unlock the potential, unlocks the potential, unlocking the potential, unlock the full potential, unlocks the full potential, unlocking the full potential, unlock the power, unlocks the power, unlocking the power, unlock the secrets, unlocks the secrets, unlock new possibilities, harness the power, harnesses the power, a beacon of, treasure trove, a symphony of, the holy grail of, a double-edged sword.
- **Use 'use'.** Write 'use'. There is no sentence where 'utilize' carries meaning that 'use' does not.
  Never use: utilize, utilise.
  Prefer: use.
- **No Latinate padding.** Choose the older, shorter word: use, start, find out, explain. Keep 'utilization' when it names a measured ratio such as CPU utilization; everything else on this list has a plain equivalent in every context.
  Never use: utilizes, utilized, utilizing, utilises, utilised, utilising, commence, commences, commenced, commencing, ascertain, ascertains, ascertained, ascertaining, endeavor, endeavors, endeavour, endeavours, aforementioned, plethora, elucidate, elucidates, elucidating.
  Prefer: use, start, find out, explain.
- **No throat-clearing frames.** Delete the frame and state the fact. If a point needs emphasis, give the reason it matters rather than announcing that it matters.
  Never use: it is important to note that, it's important to note that, it is worth noting that, it's worth noting that, it is important to remember that, it is worth mentioning that, it should be noted that, needless to say, to put it simply, in essence, at its core, generally speaking, let me be clear, i have to be honest.
- **No formulaic openers.** Open on the subject. Cut rhetorical hooks and announcements that you are about to begin.
  Never use: in the realm of, imagine a world where, picture this, have you ever wondered, look no further, whether you're a beginner or an expert, whether you are a beginner or an expert, let's dive in, let's dive into, let's break this down, buckle up, welcome to the world of.
- **No era framing.** Do not set the scene with the state of the world or the pace of the industry. Start at the specific thing you are writing about.
- **No borrowed significance.** State what the thing does and what it caused. Do not assert importance in place of a fact.
  Never use: stands as a testament to, serves as a testament to, is a testament to, serves as a reminder, plays a crucial role in, plays a pivotal role in, plays a vital role in, plays a key role in, plays a significant role in, underscores its importance, underscores the importance of, highlights its significance, left an indelible mark, rich tapestry, rich cultural tapestry, setting the stage for, marks a significant shift, represents a significant shift, a delicate balance, solidified its place, solidified its reputation, continues to captivate.
- **No engagement bait.** Trust the reader to notice what is interesting. Cut lines whose only job is to manufacture a reaction.
  Never use: here's the kicker, here is the kicker, let that sink in, read that again, no fluff, you're not imagining it, here's the part most people miss, and honestly? that's rare, curious what others think, shouting into the void.
- **No dashed reversal.** Never build a sentence around a dashed reversal: a dash into a denial, then a second dash into the correction. Make the claim once, in the affirmative.
- **Straight quotes only.** Type straight quotes and apostrophes. Curly quotes in source, comments, commit messages, or a plain-text file mean the text was pasted out of a chat window.
- **No emoji as formatting.** Use no emoji in headings, bullets, prose, commit subjects, or console output. If a line needs weight, the words carry it.
- **Comment the why, not the line.** Write a comment only where the code would surprise a reader, and make it say why. Never restate the line below it.
- **No Note or Warning labels.** Do not label a comment Note, Important, or Warning. A comment is already the note, so state the fact plainly.
- **No apologies for the code.** Never ship a comment that apologizes for the code or describes what real code would do instead. Write it, or name the gap and link the issue.
  Never use: this is a simplified implementation, this is a simplified version, this is just an example, in a production environment, you would, in production, you would want, in a real application, you would, in a real-world scenario, for demonstration purposes, replace this with your actual, this is a placeholder implementation.
- **No emoji in code or console output.** Keep emoji out of source and out of anything printed to a terminal or a log. A plain status word carries the same meaning on every encoding.
- **No self-praising identifiers.** Name code for what it does, not for how it compares to the version it replaces. Replace the old definition instead of adding enhanced_ or improved_ beside it.
- **Imperative mood, no commit narration.** Write the subject in the imperative mood, as an instruction to the codebase: "Fix null deref in parser". Never open with "This commit", "This change", or "This PR" followed by what it does.
- **No enhanced-X-to-improve-Y openers.** Name the edit, not the ambition behind it. Say what the code does now that it did not do before; a purpose clause belongs in the body only when the diff does not show it.
- **No grading your own diff.** State what changed and, if it is not obvious, why. Do not rate your own diff as robust, maintainable, clean, or production-ready; that judgment belongs to the reviewer.
  Never use: ensuring robust, ensures robust, improves maintainability, improving maintainability, improved maintainability, better maintainability, improves readability, improving readability, improves code quality, better code quality, clean and maintainable, cleaner and more maintainable, more robust and, significantly improves, greatly improves, dramatically improves, follows best practices, following best practices, industry best practices, production-ready, battle-tested, enterprise-grade, future-proof.
- **No emoji or gitmoji in commit messages.** Keep commit subjects and bodies plain text. Add gitmoji or emoji only when the repository's own history already uses them consistently, and never as decoration on a subject line.
- **No emoji in headings.** Write section headings as plain text. No emoji prefix, no decorative symbol.
- **No emoji feature bullets.** Begin a list item with the word, not a symbol. A feature list earns its place by saying what the feature does for the reader.
- **No unsupported superlatives.** Replace a speed or quality claim with the measurement that proves it, or cut the claim. Where there is no benchmark, describe what the code does instead.
  Never use: blazingly fast, blazing fast, blazing-fast, lightning fast, lightning-fast, insanely fast, buttery smooth, rock solid, rock-solid, bulletproof, battle-tested, battle tested, production-ready, production ready, enterprise-grade, enterprise grade, military-grade, industry-leading, best-in-class, best in class, world-class, world class, next-generation, next generation, supercharge, turbocharge.
- **No self-advertising headings.** Name the subject in a heading and stop. Let the section prove its own coverage.
  Never use: comprehensive, comprehensively, ultimate, definitive, exhaustive, all-in-one.
- **Lowercase kebab-case filenames.** Name documentation files in lowercase kebab-case. Reserve capitals for README.md and the conventional all-caps files a repo already keeps, such as LICENSE and CHANGELOG.md; source files follow their language's naming convention.
- **Three heading levels at most.** Nest headings no deeper than three levels in an ordinary document. When a fourth level looks necessary, either the document wants splitting or the subsection wants to be a paragraph.

## Use sparingly

Each of these is fine once. They read as machine writing when they cluster, so keep them rare and deliberate.

- **No open invitations in a document.** Close a document on its last real point. An invitation to get in touch belongs in one place, not at the end of every section.
  Watch for: feel free to reach out, feel free to ask, if you have any questions, don't hesitate to.
- **One intensity word per paragraph.** Use at most one intensity word per paragraph, and prefer the fact that made you reach for it: 'crucial' becomes 'required by the scheduler', 'robust' becomes 'survives a node restart'.
  Watch for: crucial, crucially, vital, vitally, essential, robust, robustly, comprehensive, comprehensively, sophisticated, innovative, cutting-edge, state-of-the-art, scalable, compelling, unprecedented, nuanced, powerful, valuable, notable, renowned, profound, enduring, daunting, poised, tailored, insights, excels, streamline, streamlines, streamlined, streamlining, empower, empowers, empowered, empowering, facilitate, facilitates, facilitated, facilitating, and 22 more.
- **One significance verb per paragraph.** Report the change, not its significance: 'enhances performance' becomes '18% fewer allocations'. Keep at most one of these verbs per paragraph.
  Watch for: enhance, enhances, enhanced, enhancing, emphasize, emphasizes, emphasized, emphasizing, emphasise, emphasises, emphasised, emphasising, highlights, highlighting, exemplifies, epitomizes, epitomises.
- **No connective openers.** Open paragraphs with the subject, not a connective. Keep at most one of these adverbs per paragraph, and never open two paragraphs in a row with one.
  Watch for: furthermore, moreover, additionally, consequently, subsequently, ultimately, notably, significantly, particularly, importantly, arguably, essentially, indeed, thereby, whilst, amidst, amongst.
- **Prefer is and has.** Write 'is' and 'has'. Reserve 'serves as', 'acts as', and 'represents' for sentences that mean something other than plain identity, and use at most one per paragraph.
  Watch for: serves as, serve as, served as, serving as, stands as, stand as, standing as, functions as, function as, functioning as, operates as, operating as, acts as, act as, acting as, is representative of, represents a, represents the, features a, features an, offers a range of.
- **Name the source or cut the claim.** Name the source or cut the claim. An appeal to unnamed experts or studies is fine only when the person, paper, or measurement follows it.
  Watch for: experts argue, experts agree, experts say, studies show, studies have shown, research shows, research suggests, industry reports suggest, observers have cited, some critics argue, many believe, is widely regarded as, several sources, it is often said.
- **At most one summing-up closer.** End on the last concrete point. Use at most one summing-up or forward-looking closer per document, and none in a piece short enough to reread.
  Watch for: in conclusion, in summary, to summarize, to sum up, all in all, at the end of the day, the key takeaway is, the key takeaway here is, only time will tell, the future looks bright, the future looks promising, as the field continues to evolve, one thing is clear.
- **State the affirmative claim.** Say what a thing is, not what it is not. Keep the frames 'not just X, but Y' and 'it is not X, it is Y' to at most one per document, and only where a reader would genuinely have assumed X.
- **Use the real number of items.** Use the number of items that actually exists: two reasons, or four, or one. Do not pad a list to three for cadence, and do not stack three adjectives where one measured fact works.
- **End sentences on the fact.** End the sentence on the fact. Cut trailing clauses that explain why the fact matters (', highlighting the importance of', ', underscoring', ', ensuring'), or promote the point to its own sentence with a concrete consequence.
- **No recap at the end of every section.** Stop at the last real point. Do not close every section with a recap, and do not add a summary paragraph to a piece a reader finishes in one sitting.
- **No reassurance after a limitation.** Do not answer a list of limitations with reassurance. Say what a limitation costs and where it is tracked, then stop.
  Watch for: despite these challenges, despite these limitations, despite its challenges, despite the challenges, the future looks promising, the future looks bright, the road ahead is promising.
- **Prose in paragraphs, not bullets.** Write arguments as paragraphs. Use a bullet list only for items a reader scans or counts, such as flags or ordered steps, and never nest bullets under bullets to carry reasoning.
- **One bold phrase per section.** Use bold at most once per section, for the one phrase a reader must not miss. Do not open every bullet with a bolded keyphrase or scatter bold through a paragraph.
- **Hedge once, with a reason.** Hedge once, and give the reason for the hedge. Delete the second hedge in stacks like 'could potentially', and drop caveats nobody asked for unless the risk is specific.
  Watch for: could potentially, may potentially, might potentially, potentially could, could possibly, may possibly, might possibly, consult a professional, consult a qualified professional, results may vary.
- **No question you answer yourself.** Do not ask a question you answer in the next breath. State the answer; if a question really organizes a section, make it the heading.
- **Repeat the noun.** One thing keeps one name for the whole document. If it is the parser, it stays the parser, never the engine, the component, or the solution.
- **Vary sentence length.** Vary sentence and paragraph length deliberately. Let a one-sentence paragraph stand, and do not run every paragraph through the same claim, explanation, example, wrap-up shape.
- **No numbered signposts on unordered content.** Signpost only where order is load-bearing, and let headings carry the roadmap. Drop 'firstly', 'first and foremost', and 'last but not least'.
  Watch for: firstly, secondly, thirdly, lastly, first and foremost, last but not least.
- **Headings need prose under them.** Give every heading at least a paragraph of its own before the next heading starts. Do not repeat the document title as the first heading, nest deeper than three levels, or write a heading for every two sentences.
- **No ranges between unrelated extremes.** Do not pair two unrelated extremes as a range, as in 'everything from parsing to deployment'. Name the actual scope, or list the items. Skip aphorism formulas like 'X is the language of Y'.
- **One em dash per 500 words.** Use at most one em dash per 500 words, and only for a genuine interruption. A comma or a period carries most pauses better.
- **No rule between every section.** Let headings mark section boundaries. Keep horizontal rules to one or two in a whole document, where a real change of subject earns one.
- **Sentence case in headings.** Write headings in sentence case: capitalise the first word and proper nouns, nothing else.
- **No ellipsis for suspense.** Keep the ellipsis for text you actually omitted. Do not use it to hold a beat before a reveal.
- **No exclamation marks.** State the fact and let the reader decide how to feel about it. Technical prose almost never needs an exclamation mark.
- **No drawn section banners.** Do not divide a file with drawn banner comments. A file that needs them to stay navigable should be split into modules.
- **No docstring template on trivial helpers.** Document what callers depend on. A four-line private helper whose name already says what it does needs no Args and Returns block.
- **No responsible-for docstrings.** Start a docstring with the action, in the imperative: Parse the request header. Drop framings like this function is responsible for.
  Watch for: this function is responsible for, this method is responsible for, this class is responsible for, this module provides comprehensive, this function serves as, the purpose of this function is to, this helper is designed to.
- **No numbered or leftover names.** Name a variable after what it holds: rows, parsed, retry_budget. A digit or a final suffix means two names are competing for one job.
- **Few labelled sections in a commit body.** Write the body as plain sentences about why the change was needed. Add a labelled section only when the message is long enough that a reader needs to navigate it, and at most one.
  Watch for: key changes:, summary of changes:, overview of changes:, changes made:, what changed:, key improvements:, benefits:, impact:, technical details:, implementation details:.
- **Scale the message to the diff.** Match the length of the message to the size of the change. A one-line fix gets a subject and nothing else; write a body only for reasoning a reader cannot recover from the diff.
- **PR bodies need substance, not scaffolding.** Open a PR description with the reason the change exists and what the reviewer should look at hardest. Keep a template heading only where you have something real to put under it; delete the rest.
- **Few badges, each reporting something.** Keep at most three badges, and only ones that report live state such as build status or the published version. A badge row is decoration, not evidence of use.
- **No unmeasured statistics.** State a number only when you can say where it was measured. Delete adoption counts, uptime percentages, and coverage claims that nothing in the repository backs.
- **Scale structure to the project.** Add a table of contents, a roadmap, an acknowledgements section, or an FAQ only once the project has grown enough to need one. For a single-file tool, the README is what it does, how to install it, and how to run it.
- **No text that restates its own label.** Cut an Overview that paraphrases the title, and any option table whose description column repeats the type. Keep a row when it tells the reader something the signature does not.
- **No stock documentation openers.** Open a docstring or a doc page with a verb naming what the code does. Drop the frame that announces a description is about to arrive.
  Watch for: this module provides, this package provides, this file contains functionality, this function is responsible for, this method is responsible for, this class is responsible for, is responsible for handling, provides functionality for, this document provides an overview, this section provides an overview, this guide will walk you through, in this guide, we will, the purpose of this module, the purpose of this function.
- **Write docs only when they are needed.** Create a documentation file only when it was asked for, or when a reader cannot use or build the project without it. Do not add ARCHITECTURE.md, ROADMAP.md, GOALS.md, CONTRIBUTING boilerplate, or an INSTALLATION.md for a two-line setup on your own initiative.
- **Extend a document before creating one.** Put new material in the document that already covers the topic. Start a new file only when the material fits nowhere in the existing set.
- **A heading needs prose under it.** Give a heading only to material that has developed prose beneath it, and let a short document stay one or two sections long. When a section would hold a single sentence, fold that sentence into the surrounding paragraph.
- **Tables for tabular data only.** Use a table when the data has columns a reader will compare across, and a list when the items are genuinely enumerable. Everything else is paragraphs.
- **Say why, not only what.** Write for the person who maintains this next, and record why a choice was made. Facts they can read straight from the source do not need a document.

## Task

Rewrite the text below so it follows every rule above.

Preserve the meaning, the technical content, and the author's intent exactly.
Do not add information, and do not remove information. Change only the writing.
If the text already follows the rules, say so and leave it alone.

Output only the rewritten text, with no preamble and no commentary.

$ARGUMENTS
