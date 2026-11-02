---
title: "Remote AI models"
description: "Configure OpenAI-compatible captions and SigLIP2 NaFlex search"
sidebar_position: 4
---

# Remote AI models

<Since version="1.6.0" />

An administrator can configure remote models in **Admin Area → Site Settings**.
The default models remain local.
The remote provider receives photo thumbnails and search text.
Use a provider that you trust with these inputs.
LibrePhotos sends a JPEG thumbnail without EXIF metadata.
It preserves the thumbnail aspect ratio.

## Captioning with OpenAI API

1. Select **OpenAI API** under **Captioning Model**.
2. Enter the API base **URL**. Include `/v1` if your server requires it.
3. Enter an **Access Token** if the provider requires authentication.
4. Enter the exact **Model name** that the server serves.
5. Click **Test** to check the current URL, token, and model.
6. Click **Save model settings** after the test succeeds.
7. Start **Generate captions** from the Library page.

The server must accept `POST {URL}/chat/completions` with image data URLs.
The selected model must support image input.
LibrePhotos sends the existing caption prompt and optional context.
It stores the final assistant text as the generated caption.
Manual captions remain separate.
Empty replies and failed requests do not replace captions.
The existing **LFM2.5-VL** and **None** options remain available.

For a vLLM server that requires it, enable **Disable thinking for vLLM**.
This adds `chat_template_kwargs.enable_thinking=false` to the request.
Keep this option off for servers that do not support this extension.

A saved access token never appears in the settings response.
An empty token field preserves the saved token.
Use **Remove the saved access token** to remove it.
LibrePhotos encrypts saved tokens with the application encryption key.
Retain that key when you restore a database backup.

## Search and Things with SigLIP2 NaFlex

1. Complete the library scan. Every photo needs a thumbnail.
2. Select **SigLIP2 NaFlex** under **Embedding model**.
3. Enter the embedding API base **URL** and optional **Access Token**.
4. Set **Model name** to `siglip2-so400m-patch16-naflex`.
5. Review **Advanced embedding settings** if required.
6. Click **Test** to check image and text embeddings.
7. Click **Save model settings** after the test succeeds.
8. Click **Build search index**.

The build applies to the signed-in administrator's library.
Other users build their own embeddings from the rebuild notice on their Library page.
The active model and job progress appear under the model settings.
The Library page also shows a rebuild notice when your active profile differs
from the saved settings. Use **Build search index** in that notice.
Enable semantic results in your personal **Semantic Search** setting.

The gateway must accept `POST {URL}/embeddings`.
It must accept text and image data URLs in `input`.
It must accept `max_num_patches` and return 1152 values per vector.
This image input is an extension of the OpenAI text embedding API.
An ordinary text embedding endpoint cannot process these requests.

The same model encodes images, search text, and Thing labels.
LibrePhotos normalizes the vectors before it compares them.
It uses the existing built-in and custom Thing vocabulary.
Generated Things do not replace manual Tags or ratings.

### Advanced embedding settings

- **Model revision** identifies the checkpoint served by the endpoint.
  Change this value after a checkpoint update.
- **Maximum image patches** controls the image detail budget. The default is 256.
- **Text search threshold** filters text-to-photo results. The default is 0.15.
- **Similar-photo threshold** filters photo-to-photo results. The default is 0.8.
- **Automatic things threshold** filters generated Thing labels. The default is 0.25.

The threshold values are starting values. They are not calibrated probabilities.
Evaluate them on your own photos.
SigLIP2 scores have a different scale from OpenCLIP scores.
The personal OpenCLIP Scan Confidence setting does not control these thresholds.
After you change the Thing threshold, build the index again or run **Find things**.
Stored vectors are reused when the model profile has not changed.
Use the force option for **Find things** after you change the custom vocabulary.

### Index changes and recovery

LibrePhotos keeps remote vectors separate from local OpenCLIP vectors.
The profile includes the URL, model, revision, patch budget, and preprocessing.
A profile change requires a new index build.
A token change does not require a new build.
If the checkpoint revision changes behind the same URL and model name,
LibrePhotos pauses text-to-photo search until the rebuild completes.
The server cannot select the earlier checkpoint by revision alone.
Metadata search and existing similar-photo results remain available.
Search uses the previous active model while a replacement builds.
The new model becomes active after all vectors and the index are stored.

A failed or cancelled build retains completed vector batches.
Start **Build search index** again to reuse those batches.
After a container restart, cancel an interrupted job in **Jobs** if it still
shows as running. Then start a new build.
LibrePhotos does not automatically resume an interrupted job.

To return to **OpenCLIP**, select it, save, and build the index again.
The previous vectors remain stored for reuse.
Model settings and vectors survive normal Docker image replacement.
Keep the database, application key, and protected media on persistent storage.

## Test before saving

**Test** uses the current form values and a small synthetic image.
Captioning must return caption text. Embeddings must return valid image and text vectors.
The test does not read a library photo or save the draft settings.
It does not change the selected model, create a job, or rebuild the index.
A blank token field reuses the saved token. **Remove the saved access token**
tests without that token. The saved token stays unchanged until you save.

The button shows progress. A result appears beside the controls.
Changing a field hides the earlier result. Fix a failed test and try again.
A successful test checks connectivity and the response format.
It does not measure caption or search quality. Saving is a separate action.

## Local sidecars

Selecting **OpenAI API** stops use of the local captioning sidecar.
Selecting **SigLIP2 NaFlex** stops local OpenCLIP processing after every active
library has moved to the remote model.
The local encoder remains available while an active library still uses it.
Face recognition and OCR keep their existing configuration.

## Provider errors

Requests have bounded connection and response timeouts.
LibrePhotos rejects redirects and malformed embedding vectors.
The Jobs page reports provider failures without provider response bodies or tokens.
If text embedding requests fail, metadata search remains available.
