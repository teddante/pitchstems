# Source Separation Research Notes

Research date: 2026-05-22

## Short Answer

There is no single universal "best" open source stem separator. The answer depends on the task:

- Best vocal/instrumental quality: RoFormer-family models and ensembles.
- Best multi-stem quality: ensemble systems, with BS RoFormer SW as the most interesting local six-stem target.
- Best bass/drums/other reliability: Demucs HT/HT fine-tuned remains useful.
- Native-first integration target: `bs-roformer-infer` for BS-RoFormer and `basic-pitch` for MIDI. `audio-separator` is useful as a compatibility reference, but it is no longer the default PitchStems runtime.

## Highest Scoring Families

### Ensemble Systems

MVSep's current public quality tables show the highest numbers for ensembles. The latest vocal/instrumental ensemble listed, 2025.06, combines BS RoFormer, MelBand RoFormer, and SCNet XL IHF and reports:

- Multisong vocals SDR: 11.93
- Multisong instrumental SDR: 18.23
- Synth vocals SDR: 14.46
- Synth instrumental SDR: 14.17

For a broader vocals/instrumental/bass/drums/other ensemble, MVSep lists a 2025.06.30 version with:

- Average SDR: 13.67
- Bass: 14.85
- Drums: 14.33
- Other: 9.00
- Vocals: 11.93
- Instrumental: 18.23

This is the quality ceiling, but it is usually slow and made from multiple models.

Source: https://mvsep.com/en/algorithms

### BS RoFormer

BS RoFormer is one of the strongest research-backed model families. The original paper says the SAMI-ByteDance system ranked first in the SDX23 music separation track, and a smaller version reached 9.80 dB average SDR on MUSDB18HQ without extra training data.

MVSep's later BS RoFormer 2025.07 vocal/instrumental table reports:

- Multisong vocals SDR: 11.89
- Multisong instrumental SDR: 18.20
- Synth vocals SDR: 14.58
- Synth instrumental SDR: 14.28

Source: https://arxiv.org/abs/2309.02612  
Source: https://mvsep.com/en/algorithms

### BS RoFormer SW

BS RoFormer SW is especially interesting for PitchStems because it outputs six stems directly:

- vocals
- drums
- bass
- guitar
- piano
- other

MVSep lists it with:

- vocals: 11.30
- instrumental: 17.50
- bass: 14.62
- drums: 14.11
- guitar: 9.05
- piano: 7.83
- other: 8.71

`bs-roformer-infer` also recommends BS-RoFormer-SW as its default production model.

Source: https://mvsep.com/en/algorithms  
Source: https://github.com/openmirlab/bs-roformer-infer

### MelBand RoFormer

The Mel-Band RoFormer paper says it outperforms BS-RoFormer on vocals, drums, and other stems on MUSDB18HQ. In practical model tables, it is very strong for vocal/instrumental separation, though the newest BS RoFormer variants and ensembles currently edge it out in MVSep's tables.

MVSep lists MelBand RoFormer 2024.10 at:

- Multisong vocals SDR: 11.28
- Multisong instrumental SDR: 17.59
- Synth vocals SDR: 13.89
- Synth instrumental SDR: 13.59

Source: https://arxiv.org/abs/2310.01809  
Source: https://mvsep.com/en/algorithms

### SCNet

SCNet is lower-compute and strong. The paper reports 9.0 dB SDR on MUSDB18-HQ without extra data, and CPU inference time at 48% of HT Demucs. MVSep says SCNet is close to RoFormer quality and sometimes better on specific tracks, but still slightly behind the top RoFormer models.

Source: https://arxiv.org/abs/2401.13276  
Source: https://mvsep.com/en/algorithms

### Demucs HT

Demucs is no longer the top-end vocal/instrumental separator, but it remains useful for 4-stem song separation. MVSep explicitly describes Demucs4 HT as currently best for bass/drums/other separation, with htdemucs_ft as best quality among the Demucs variants.

Source: https://mvsep.com/en/algorithms

## Benchmark Caveat

SDR is useful but not the whole story. In the SDX23 paper, SAMI-ByteDance ranked first by SDR on the Standard leaderboard at 9.97 dB, followed by ZFTurbo at 9.26 and kimberley_jensen at 9.18. But the listening-test TrueSkill ranking put kimberley_jensen first, ZFTurbo second, and SAMI-ByteDance third.

So PitchStems should support model comparison and ensembles rather than only a single "best" button.

Source: https://transactions.ismir.net/articles/10.5334/tismir.171

## Practical PitchStems Methods

The app now exposes a native-first BS-RoFormer catalog:

- `bs_roformer_sw`: native BS-RoFormer SW for vocals, drums, bass, guitar, piano, other, plus instrumental.
- `bs_roformer_vocals_resurrection`: native vocal-specialist BS-RoFormer.
- `bs_roformer_vocals_revive_v3e`: native vocal-specialist BS-RoFormer with fuller capture bias.
- `bs_roformer_instrumental_resurrection`: native instrumental-specialist BS-RoFormer.
- `bs_roformer_dereverb`: native BS-RoFormer repair model.

## Best Next Product Features

1. Add a "Compare models" workflow that runs multiple compatible models and lets the user audition outputs.
2. Add model download status and disk usage display.
3. Add a dedicated drum-to-MIDI model later; Basic Pitch should not be expected to produce good drum MIDI.
4. Add more low-level architecture controls behind an expert toggle once the core builder is stable.

## Native Backend Options Exposed

PitchStems now talks to `bs-roformer-infer` directly for separation and to Spotify `basic-pitch` directly for MIDI. The important visible controls are:

- native BS-RoFormer registry id
- checkpoint filename
- config filename
- supported output stems
- single-stem export filtering after separation
- Basic Pitch MIDI policy

Audio Separator remains useful research context for model scores and odd community checkpoints, but it is not the default runtime path.

## UI Transparency Rules

The GUI should make the chain of cause and effect obvious:

1. "Parts to create" is only a filter. It narrows the method table to models that can produce those parts.
2. The method table must show outputs, score evidence, and speed before the user picks a method.
3. The SDR chart should make comparison visual, but it must explain that higher SDR is only a direct "better" signal when the stem/task is comparable.
4. Stem choices come from the selected method, because different methods physically cannot output the same parts.
5. "Processing effort" changes overlap, repeated passes, or shifts where the architecture supports those knobs.
6. Peak normalization and chunking are technical controls. They stay available, but hidden by default because they are not part of the core musical decision.

SDR scores are shown where they exist, but the UI should never imply that one number is the full answer. Ensembles, bleed-control presets, and repair models often have task-specific evidence rather than one directly comparable score.
