---
title: "📝 Image Captioning"
description: "What is image captioning and how do I use it?"
sidebar_position: 9
---

## What is image captioning?

The goal of automatic image captioning is to understand the content of an image and then produce a coherent and contextually relevant sentence or phrase that describes what is happening in the image.

To use the feature, open one of your own photos and click the information icon in the top bar to show the details panel. In the **Caption** section, click the pencil icon in the top-right corner of the caption box to start editing, then click the wand icon that appears in its place. Once a caption has been generated, it appears as a suggestion just above the caption box — click it to drop the text into the caption field, then press the green tick below the box to save it. (If a caption has already been generated for this photo, the suggestion appears as soon as you start editing.) The wand, cancel and tick controls are only shown while you are editing, and captions cannot be generated on publicly shared photos.

## Captioning the whole library {#captioning-the-whole-library}

<Since version="1.4.0" /> To caption many photos at once, open **Account menu > Library**. Under the **Captions** heading is the **Generate captions** row:

- **Generate** captions the photos that have no generated caption yet. The first time, that is all of your photos; after that, the photos added since. A run you cancelled continues where it stopped the next time you click **Generate**.
- The arrow next to **Generate** opens **Generate captions again for all photos**, which writes a new generated caption for every photo. It asks first, because on a large library it runs for hours.

Both start a **Generate Captions** job, which you can follow under **Account menu > My Jobs** and cancel there. It captions photos only, not videos, and skips photos in the trash and photos that have no thumbnail yet. Each user runs it for their own photos. A caption you wrote yourself is never changed: the job only writes the generated caption, which search finds next to yours.

The job does not run by itself after a scan. When you have added new photos, click **Generate** again. It takes the time of one caption per photo (see below), so a library of 30,000 photos at about 2 seconds a photo keeps the job queue busy for around 17 hours; other jobs, such as a scan, wait until it has finished or you cancel it. A job that keeps making progress is not stopped by the [stuck-job check](./job-system.md#what-to-do-when-a-job-gets-stuck), however long it runs.

The **Captions** section is only shown while captioning is on: the **Image captioning** switch in the [Features card](./feature-toggles.md#site-settings-switches) is on and `Captioning Model` is not `None`. When the captioning model is not downloaded yet, the job downloads it first and then starts captioning.

## Which model writes the captions?

The default local caption model is [LFM2.5-VL](https://huggingface.co/LiquidAI/LFM2.5-VL-450M), a small vision-language model from Liquid AI that runs on ONNX Runtime like every other model in LibrePhotos. Its files (about 370 MB) are fetched with the other models while local captioning is on. An administrator can also select an [OpenAI-compatible provider](./settings/remote-ai.md) in the Admin Area. <Since version="1.4.0" /> With captioning turned off they are not downloaded; turning it on again downloads them when you save the site settings or ask for a caption. The model needs about 0.9 GB of RAM while it captions and takes a few seconds per photo on an older desktop CPU, under a second on a recent one.

It writes one natural sentence, for example "A rocket is taking off from a launch pad at night, with two tall metal towers flanking the launch site." Because it is a vision-language model it also takes instructions, which is what the caption context settings below use.

To turn automatic captioning off, set `Captioning Model` to `None` in the `Admin Area`; an administrator can also switch the feature off for the whole deployment with the `FEATURE_IMAGE_CAPTIONING` environment variable. The earlier captioning models (im2txt, BLIP, Florence-2 and Moondream) and the separate Mistral language model were retired; an install that had any of them selected is moved to LFM2.5-VL automatically.

## Caption context: names and places

LibrePhotos can use face recognition and reverse geocoding to add names and places to captions. The model receives the location and face references. LibrePhotos resolves trusted names after inference. Each user controls this in their own `Settings`, under **Caption Context**:

- **Tell the captioning model what LibrePhotos knows about a photo** turns the context on. Default `On`.
- **Use the names of recognised people in captions** allows trusted face labels in generated captions. Default `On`. See the face identity rules below.
- **Mention where the photo was taken in captions** adds the photo's geocoded location. Only has an effect when the photo has one. Default `On`.

With the context switched off, the model is simply asked to describe the photo.

## Face identities and caption updates

<Since version="1.6.0" />

LibrePhotos can update a generated caption after it identifies a face.
For example, "A person is wearing a hat" can become "Alexander is wearing a hat".

The model receives a temporary copy of the thumbnail with numbered face boxes.
The prompt gives each box a stable reference token and its pixel coordinates.
The model describes people through these references.
LibrePhotos replaces a reference with a trusted name after the model responds.
The face database's personal names are not sent in the caption prompt.
The original photo and thumbnail stay unchanged.

An existing confirmed face label is eligible when it names one of the owner's people.
Imported named face regions use the same label field as confirmed labels.
An inferred identity requires agreement between classification and clustering.
Both finite scores must reach **0.99** or your higher person-confidence threshold.
This threshold is a model score. It is not a measured correctness probability.
Unknown people, rejected identities, other owners' people, invalid or ambiguous boxes,
and faces from later video frames do not supply names.

A generated caption stores its face references internally.
A rename, corrected label, or confidence loss updates the displayed generated text
without another model call when the face geometry stays unchanged.
If a face no longer qualifies, its reference becomes "a person".
New or changed boxes queue a fresh caption request.
An outdated response cannot overwrite newer face information.
Internal face evidence stays out of photo API responses and shared search.

A caption that you saved manually stays unchanged.
This also applies to an AI suggestion that you copied into your manual caption.
Generated caption updates refresh search and the photo's modification timestamp.
The Caption Context switches continue to control name use.

Previously generated captions need one fresh model pass before local name updates
and confidence-based anonymization can use their face references.
Face changes queue that pass for an existing generated caption.
You can also use **Generate captions again for all photos** to refresh the library.
**Generate** retries captions marked stale after a failed update.
Provider failures preserve the current safe generated text and your manual caption.

Face recognition confidence does not prove that the VLM associated an action
with the correct face. Review important captions.
A model that omits the reference tokens can leave the caption anonymous.
