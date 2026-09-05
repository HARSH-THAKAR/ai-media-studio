# Hitting a target length

Making the finished video come out the length you asked for is the part of this
pipeline that needed the most measurement. What follows is what it took, and
what the numbers actually were.

## Length is decided at script time or not at all

A video runs exactly as long as its narration. You cannot trim your way to a
target without either cutting a sentence in half or leaving a shot on screen in
silence. So the length is decided when the script is written, or it is not
decided at all.

Which means the whole problem reduces to: get the model to write a specific
number of words.

An 8B model is bad at this. That is the finding, and it is not surprising. What
was surprising is *how* it is bad, because that turned out to matter far more
than how much.

## Attempt one: ask for a word count

The obvious thing. Work out how many words fit in 30 seconds, put that in the
prompt, ask for a script.

On `llama3.1:8b`, a word budget for the whole script **missed by a median of
36%**, and the misses ranged from **66% short to 30% long**.

That range is the problem, not the median. A 36% median error you could imagine
correcting. A distribution that swings from two-thirds short to a third long has
nothing stable in it to correct *for*. Any fudge factor that fixes the short
case makes the long case worse.

## Attempt two: ask per scene

Same total budget, expressed differently. Instead of "write a 66 word
script", the prompt says how many words each scene's narration should be.

**Median miss: 18%.** Better, but that is not the interesting part.

The interesting part is that it missed *consistently*. Nearly every result came
in short, rather than scattering either side. The error stopped being noise and
became a bias.

**A consistent bias can be cancelled. Noise cannot.** An 18% error whose
direction you can predict is worth more than an 8% error you cannot — you just
ask for more than you want:

```python
# Models write short. Measured on llama3.1:8b, a per-scene word budget was
# undershot by a median of 18%, so the budget asked for is raised to land on
# the target rather than below it.
SCRIPT_LENGTH_CORRECTION = 1.22
```

That is the whole trick, and I think it generalises well beyond this project.
When you are measuring how badly a model follows an instruction, **measure the
shape of the error, not just its size.** A big consistent error is a solved
problem. A small inconsistent one is not.

Why per-scene works better is worth a guess: "write 66 words" asks the model to
track a budget across a structure it is still inventing. "Write 11 words of
narration for this scene" is a local constraint it can satisfy one scene at a
time, and small errors average out instead of compounding.

## The second problem: words per second is not a constant

Converting seconds to words needs a speaking rate. I measured one from a real
narration and hardcoded it:

```python
# How fast this voice speaks at speed 1.0, measured over a finished narration:
# 75 words in 33.65 seconds.
WORDS_PER_SECOND = 2.23
```

Then a different script came out at **1.98** words a second.

The rate is not a property of the voice. It is a property of the voice *and the
words*. "Bioluminescent" takes longer to say than "cat", and a script about
deep-sea biology is full of the former. A constant that is right for one topic
is 11% wrong for the next.

So the rate cannot be assumed. It has to be observed.

## Two loops, one cheap and one honest

The design that came out of this has two feedback loops at different costs.

**The cheap loop** runs before anything expensive. A script's spoken length can
be estimated from its word count for free, so a script that would run badly long
or short is thrown away and asked for again — before the images, the narration
and the render happen.

```python
for attempt in range(1, SCRIPT_LENGTH_ATTEMPTS + 1):
    script = _parse_script(self._request(_script_prompt(topic, style, length)))
    spoken = length.seconds_for(_spoken_words(script), len(script[3]))
    miss = abs(spoken - length.target_seconds) / length.target_seconds
    if miss < best_miss:
        best, best_miss = script, miss
    if miss <= SCRIPT_LENGTH_TOLERANCE:
        return script
```

Three attempts, 15% tolerance, and it keeps the closest one if none land. A miss
costs one model call — the cheapest stage in the run — rather than a whole
generation.

**The honest loop** runs after narration, because the estimate rests on that
speaking rate, and the speaking rate is a guess until the voice has actually
spoken. Once it has, the real rate is known, and a script that missed gets
rewritten at the rate this narration just demonstrated:

```python
def _recalibrated(length, storyboard, measured_seconds):
    """Replace the assumed speaking rate with the one just measured."""
    words = sum(len(scene.narration.split()) for scene in storyboard.scenes)
    speech = measured_seconds - length.padding_seconds_per_scene * len(storyboard.scenes)
    if words <= 0 or speech <= 0:
        return length
    return replace(length, words_per_second=words / speech)
```

The first loop is prediction. The second is measurement. The second one is what
actually works; the first one just makes it cheap to get there.

## The bug that made all of it useless

Here is the part I would rather leave out, which is exactly why it is worth
including.

I shipped all of the above, ran a 30 second generation, and got **37.85
seconds** — a 26% overrun. Every mechanism described above was working
correctly, and the result was worse than useless, because a length control that
is confidently 26% wrong is worse than none at all.

Three causes, none of them in the length code:

- The **opening hook** is generated separately from the scene narrations, and it
  is spoken. Nothing counted its words.
- The speaking rate was the hardcoded 2.23 and this script ran at 1.98.
- Each scene holds for a moment after its narration ends. That silence is part
  of the finished video. It was not in the budget.

Every one of them sits in a **seam between two individually-correct
components**. The hook generator was right. The budget calculator was right. The
renderer's scene padding was right. The length was wrong because nothing owned
the sum.

None of it was caught by a passing test suite, because every unit was doing its
job. It was caught by watching one video and noticing it felt long.

The fix was to make the budget account for what actually gets spoken and what
actually gets held:

```python
def words_for(self, scenes: int) -> int:
    # The silence left after each scene is part of the finished length, so it
    # comes out of the budget rather than being added on top of it.
    speech = self.target_seconds - self.padding_seconds_per_scene * scenes
    return max(1, round(speech * self.words_per_second))
```

Same topic, after: **28.9 seconds**.

## Results

Three 30 second targets, one command each, nothing hand-edited:

| Topic | Asked | Got |
| --- | --- | --- |
| Why Neutron Stars Spin So Fast | 30s | 29.3s |
| Why Venice Is Sinking | 30s | 31.3s |
| How Bees Decide Where To Live | 30s | 33.5s |

The worst of those is 11.7% out, inside the 15% tolerance. I have not tested
long-form: everything above is measured at around 30 seconds, and I would not
claim it holds at five minutes.

## What I would take from this

1. **Measure the shape of the error, not just its size.** A consistent 18% miss
  is more useful than a random 8% one, because you can cancel a bias and you
  cannot cancel noise.
2. **Local constraints beat global ones.** Per-scene budgets outperformed a
  whole-script budget on an 8B model, probably because the model does not have
  to track a running total across a structure it is still inventing.
3. **Do not hardcode a rate you can measure.** Anything that varies with content
  will eventually vary in a way that embarrasses you.
4. **Cheap checks before expensive stages.** One wasted model call beats one
  wasted generation.
5. **The bug will be in the seam.** All three real defects here lived between
  components that were each individually correct, and the test suite passed
  straight through every one of them.

The settings that drive all of this, `video.target_duration_seconds` among them,
are documented in [CONFIGURATION.md](CONFIGURATION.md). The code lives in
`backend/providers/ollama.py`, `backend/providers/contracts.py` and
`backend/workflow/reel_workflow.py`.
