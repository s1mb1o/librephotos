# Test remote model settings

Date: 2026-11-02
Status: Implemented and validated. The owner requested the Test action.

Add Test beside Save model settings for each remote provider.
Use the current form values. Do not save or select a model during a test.
Reuse a saved token when the token field is blank. Honor Clear saved token.
Validate request fields with the existing remote settings serializer.
Expose POST /api/sitesettings/test-model/ to administrators only.
Return the provider kind and a nullable embedding dimension on success.
Return sanitized provider errors through the existing API error format.

Create a temporary synthetic JPEG. Do not read a library photo.
Captioning must return nonempty image caption text.
SigLIP2 must return valid 1152-dimensional image and text vectors.
Use the same inference clients, preprocessing, and bounded timeouts as normal work.
Do not create jobs, cached vectors, model downloads, or index changes.
Show pending, success, and failure states beside the buttons.
Hide a test result when the form no longer matches the tested values.
Saving remains an independent action.

Verify admin authorization, unsaved values, token reuse and clearing,
provider errors, malformed responses, no database changes, and UI feedback.
