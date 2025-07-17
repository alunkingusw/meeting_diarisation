import logging


# Configure logging level and format
logging.basicConfig(
    level=logging.INFO,  # options: DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()  # prints to console
    ]
)


#LIBRARIES

#transcription
import whisper

#audio handling
import torch
import torchaudio

#diarisation
from pyannote.audio import Pipeline
from pyannote.audio import Model
from pyannote.core import Segment, Annotation

#embedding
from pyannote.audio import Inference
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize
import numpy

#other
import datetime
from collections import defaultdict
import os

#file handling
#from google.colab import drive, userdata

#set up files to load
#logging.info("Mounting Google Drive. Please follow the instructions to authenticate.")
#drive.mount('/content/drive')

# Get Hugging Face token stored in Colab Secrets
HUGGING_FACE_TOKEN = os.getenv("HUGGING_FACE_TOKEN")


# Use the path to your audio file in Google Drive
input_file = '/content/drive/My Drive/ColabFiles/AudioFiles/ThisAmericanLifeEpisodeOne.wav'

#organise the inputs for the transcription pipeline
NUM_SPEAKERS = 9
language = 'English'
model_size = 'medium'
model_name = model_size
#name according to available models outlined on https://github.com/openai/whisper?tab=readme-ov-file#available-models-and-languages
if language == 'English' and model_size != 'large':
  model_name += '.en'

#inputs for the embedding process
SNR_THRESHOLD = 5.0
MIN_SEGMENT_DURATION = 5.0
EMBEDDING_MATCH_THRESHOLD = 0.7

#MODELS
#diarisation by Pyannote
pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization", use_auth_token=HUGGING_FACE_TOKEN)
#transcription by Whisper
model = whisper.load_model(model_name)


# Move models to the GPU if available
if torch.cuda.is_available():
    pipeline.to(torch.device("cuda"))
    model.to(torch.device("cuda"))
    logging.info("Pyannote and Whisper models moved to GPU")
else:
    logging.info("GPU not available, Pyannote and Whisper models running on CPU")

# Perform the intensive stuff - transcription
#asr_result = model.transcribe(input_file)
diarisation_result = pipeline(input_file, num_speakers=NUM_SPEAKERS)

# ------ This next section deals with the embeddings and comparison used to label speakers ------

# Declare our functions used for various stages of embedding comparison
def crop_waveform(waveform, sample_rate, segment):
    """Return waveform cropped to the specified segment."""
    start_sample = int(segment.start * sample_rate)
    end_sample = int(segment.end * sample_rate)
    return waveform[:, start_sample:end_sample]

def get_reference_embeddings(ref_dict):
    """Return dictionary of normalized reference embeddings."""
    embeddings = {}
    for i, (name, path) in enumerate(ref_dict.items()):
        try:
            emb = embedding_inference(path).reshape(1, -1)
            emb = normalize(emb)
            embeddings[i] = emb
            logging.info(f"Loaded reference embedding for '{name}' as ID {i}")
        except Exception as e:
            logging.warning(f"Error loading reference '{name}': {e}")
    return embeddings

def match_speaker_by_embedding(embedding, speaker_embeddings, speaker_names, threshold=EMBEDDING_MATCH_THRESHOLD):
    """Return the best matching speaker name based on cosine similarity."""
    best_match = None
    highest_similarity = -1

    # Compare with reference embeddings
    for ref_id, ref_embedding in speaker_embeddings.items():
        similarity = cosine_similarity(embedding, ref_embedding)[0][0]
        if similarity > highest_similarity:
            highest_similarity = similarity
            best_match = speaker_names[ref_id]
    logging.info(f"Highest similarity with '{best_match}': {highest_similarity}")
    if highest_similarity >= threshold:
        return best_match
    else:
        return None

def remove_speaker_from_diarisation(diarisation, speaker_to_remove):
    """Return a copy of diarisation with the specified speaker removed."""
    new_diarisation = Annotation(uri=diarisation.uri)

    for segment, track, speaker in diarisation.itertracks(yield_label=True):
        if speaker != speaker_to_remove:
            new_diarisation[segment, track] = speaker

    return new_diarisation

#load speaker samples and generate the embeddings to be tested below
embedding_model = Model.from_pretrained("pyannote/embedding",
                              use_auth_token=HUGGING_FACE_TOKEN)
# Move model to GPU if available
if torch.cuda.is_available():
    embedding_model.to(torch.device("cuda"))
    logging.info("Embedding model moved to GPU")
else:
    logging.info("GPU not available, embedding model running on CPU")

embedding_inference = Inference(embedding_model, window="whole")

# Load full audio for cropping our speaker clips
waveform, sample_rate = torchaudio.load(input_file)  # mono only

# Define the dictionary of known speaker names and the sample audio
speaker_samples = {
    "ira_glass": "/content/drive/My Drive/ColabFiles/AudioFiles/ira_glass.wav",
    "ed_ryder": "/content/drive/My Drive/ColabFiles/AudioFiles/ed_ryder.wav",
    "joe_franklin": "/content/drive/My Drive/ColabFiles/AudioFiles/joe_franklin.wav",
    "kevin_kelly": "/content/drive/My Drive/ColabFiles/AudioFiles/kevin_kelly.wav",
    "lawrence_steger": "/content/drive/My Drive/ColabFiles/AudioFiles/lawrence_steger.wav",
    "receptionist": "/content/drive/My Drive/ColabFiles/AudioFiles/receptionist.wav",
    "shirley_glass": "/content/drive/My Drive/ColabFiles/AudioFiles/shirley_glass.wav",
}
#turn those files into embeddings
speaker_embeddings = get_reference_embeddings(speaker_samples)

# Use diarisation from previous code block to loop through identified speakers
# diarisation_result

# Group segments by speaker so we can run comparisons
segments_by_speaker = defaultdict(list)
for turn, _, speaker in diarisation_result.itertracks(yield_label=True):
    segments_by_speaker[speaker].append(Segment(turn.start, turn.end))

# Load SNR model which will help identify the best audio clip to compare
snr_model = Model.from_pretrained("pyannote/brouhaha", use_auth_token=HUGGING_FACE_TOKEN)

# Move model to GPU if available
if torch.cuda.is_available():
    snr_model.to(torch.device("cuda"))
    logging.info("SNR model moved to GPU")
else:
    logging.info("GPU not available, SNR model running on CPU")

# apply model
snr_inference = Inference(snr_model)

# Step through each speaker label and its associated segments from diarisation
for speaker, segments in segments_by_speaker.items():
    valid_embeddings = []

    # Process each segment for that speaker
    for segment in segments:
        duration = segment.end - segment.start

        # Ignore short segments if there are other longer ones
        if duration < MIN_SEGMENT_DURATION and len(segments) > 1:
            continue

        # Crop audio to just this segment
        cropped = crop_waveform(waveform, sample_rate, segment)

        # Apply SNR model to filter out low-quality audio
        snr_result = snr_inference({"waveform": cropped, "sample_rate": sample_rate})
        snr_values = [snr for frame, (vad, snr, c50) in snr_result if vad > 0.5]

        if not snr_values:
            continue  # skip if there's no speech

        avg_snr = sum(snr_values) / len(snr_values)

        if avg_snr < SNR_THRESHOLD:  # optional threshold to skip noisy clips
            continue

        # Compute embedding for this valid segment
        embedding = embedding_inference({
            "waveform": cropped,
            "sample_rate": sample_rate
        }).reshape(1, -1)

        embedding = normalize(embedding)
        valid_embeddings.append(embedding)

    # Average the embeddings for this speaker if any were collected
    if valid_embeddings:
        mean_embedding = numpy.mean(numpy.vstack(valid_embeddings), axis=0, keepdims=True)

        match = match_speaker_by_embedding(mean_embedding, speaker_embeddings, list(speaker_samples.keys()))

        if match:
            logging.info(f"Speaker '{speaker}' best matches reference speaker: {match}")
            # rename speakers if you know their name
            diarisation_result = diarisation_result.rename_labels({speaker: match})

        else:
            logging.info(f"Speaker '{speaker}' could not be confidently matched and will be removed.")
            #diarisation_result = remove_speaker_from_diarisation(diarisation_result, speaker)
    else:
        logging.info(f"No valid segments found for speaker '{speaker}', removing from diarisation.")
        #diarisation_result = remove_speaker_from_diarisation(diarisation_result, speaker)

# finally, merge the diarisation results with the whisper output and export to terminal.
# we do this by running whisper on each segment
from pyannote.audio import Audio
audio = Audio(sample_rate=16000, mono=True)

for segment, _, speaker in diarisation_result.itertracks(yield_label=True):
    waveform, sample_rate = audio.crop(input_file, segment)
    text = model.transcribe(waveform.squeeze().numpy())["text"]
    print(f'{segment.start:06.1f} {segment.end:06.1f} {speaker} "{text}"')
