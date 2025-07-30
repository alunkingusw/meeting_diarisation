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

#database
from sqlalchemy.orm import Session
from sqlalchemy import and_
from backend.models import RawFile, Meeting

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
import uuid

#file handling
from backend.config import settings
from pathlib import Path

#set up files to load
#logging.info("Mounting Google Drive. Please follow the instructions to authenticate.")
#drive.mount('/content/drive')

# Get Hugging Face token stored in Colab Secrets
HUGGING_FACE_TOKEN = os.getenv("HUGGING_FACE_TOKEN")

def transcribe_meeting(group_id: int, meeting_id: int, db: Session, snr_threshold = 5.0, embedding_match_threshold = 0.7):
    #inputs for the embedding process
    SNR_THRESHOLD = snr_threshold
    MIN_SEGMENT_DURATION = 5.0
    EMBEDDING_MATCH_THRESHOLD = embedding_match_threshold

    # Find first audio file for this meeting
    audio_file = db.query(RawFile).filter(
        and_(
            RawFile.meeting_id == meeting_id,
            RawFile.type == "audio"
        )
    ).first()

    if not audio_file:
        logging.warning(f"Audio file for meeting id {meeting_id} not found in database to process.")
        return;

    # Get audio file path
    audio_dir = settings.UPLOAD_DIR
    input_file = audio_dir / audio_file.file_name
    #check file exists before processing
    if not input_file.exists():
        logging.warning(f"Audio file at {input_file} not found to process.")
        return;

    

    #organise the inputs for the transcription pipeline. Num speakers is taken from the attendance on the database
    # Find meeting based on the meeting_id
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id,
    ).first()

    if not meeting:
        logging.warning(f"Meeting id {meeting_id} not found in database, cannot proceed transcription")

    num_attendees = len(meeting.attendees)
    logging.info(f"Processing transcription file with {num_attendees} attendees.")

    NUM_SPEAKERS = num_attendees
    language = 'English'
    model_size = 'medium'
    model_name = model_size
    #name according to available models outlined on https://github.com/openai/whisper?tab=readme-ov-file#available-models-and-languages
    if language == 'English' and model_size != 'large':
        model_name += '.en'

    #MODELS
    #diarisation by Pyannote
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization", use_auth_token=HUGGING_FACE_TOKEN)
    #transcription by Whisper
    transcription_model = whisper.load_model(model_name)


    # Move models to the GPU if available
    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))
        transcription_model.to(torch.device("cuda"))
        logging.info("Pyannote and Whisper models moved to GPU")
    else:
        logging.info("GPU not available, Pyannote and Whisper models running on CPU")

    # Perform the intensive stuff - transcription
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

    def match_speaker_by_embedding(embedding, speaker_embeddings, threshold=EMBEDDING_MATCH_THRESHOLD):
        """
        Matches an input embedding against a list of known speaker embeddings.
    
        Parameters:
            embedding (list of float): The embedding to match.
            speaker_embeddings (list of dict): Each dict should have 'id', 'name', and 'embedding'.
            threshold (float): Cosine similarity threshold for a valid match.

        Returns:
            str or None: Best matching speaker name, or None if no match is above threshold.
        """
        best_match = None
        highest_similarity = -1

        # Compare with reference embeddings
        for speaker in speaker_embeddings.items():
            similarity = cosine_similarity(embedding, speaker["embedding"])[0][0]
            if similarity > highest_similarity:
                highest_similarity = similarity
                best_match = speaker
        logging.debug(f"Highest similarity: {highest_similarity:.4f} (match: '{best_match}')")
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

    attendee_embeddings = []

    for attendee in meeting.attendees:
        if attendee.embedding:
            attendee_embeddings.append({
                "id": attendee.id,
                "name": attendee.name,
                "embedding": attendee.embedding,
            })
    logging.info(f"Embeddings for {len(attendee_embeddings)} out of {len(meeting.attendees)} generated.")
    # Use diarisation from previous code block to loop through identified speakers

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

            match = match_speaker_by_embedding(mean_embedding, attendee_embeddings)

            if match:
                logging.info(f"Speaker '{speaker}' best matches reference speaker: {match['name']}")
                # rename speakers if you know their name
                diarisation_result = diarisation_result.rename_labels({speaker: match['name']})

            else:
                logging.info(f"Speaker '{speaker}' could not be confidently matched.")
                #diarisation_result = remove_speaker_from_diarisation(diarisation_result, speaker)
        else:
            logging.info(f"No valid segments to compare found for speaker '{speaker}'.")
            

    # finally, merge the diarisation results with the whisper output and export to terminal.
    # we do this by running whisper on each segment
    from pyannote.audio import Audio
    audio = Audio(sample_rate=16000, mono=True)

    def format_timestamp(seconds: float) -> str:
        """Convert seconds to WebVTT timestamp format (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02}:{minutes:02}:{secs:02}.{millis:03}"

    vtt_lines = ["WEBVTT\n"]
    index = 1

    for segment, _, speaker in diarisation_result.itertracks(yield_label=True):
        waveform, sample_rate = audio.crop(input_file, segment)
        text = transcription_model.transcribe(waveform.squeeze().numpy())["text"]

        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        
        vtt_lines.append(f"{index}")
        vtt_lines.append(f"{start} --> {end}")
        vtt_lines.append(f"{speaker}: {text.strip()}")
        vtt_lines.append("")  # blank line between entries
        index += 1
    
    # Build human-readable name for subtitle file
    audio_base_name = Path(audio_file.human_name).stem
    human_filename = f"{audio_base_name}.vtt"

    # Safe UUID-based file name
    safe_filename = f"{uuid.uuid4().hex}_{human_filename}"
    
    # Build the target directory
    target_dir = settings.UPLOAD_DIR / str(group_id) / str(meeting_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest_path = target_dir / safe_filename


    # Write to disk
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(vtt_lines))

    
    # finally, update the database for the status of the transcription.
    # Check for existing transcript entry for this meeting
    existing_transcript = db.query(RawFile).filter_by(
        meeting_id=meeting_id,
        type="transcript_generated"
    ).first()

    if existing_transcript:
        db.delete(existing_transcript)
        db.commit()

    # Create new RawFile entry for the transcript
    transcript_file = RawFile(
        file_name=safe_filename,
        human_name=human_filename,
        description="Auto-generated transcript",
        meeting_id=meeting_id,
        type="transcript_generated",
        processed_date=datetime.utcnow()
    )
    db.add(transcript_file)
    db.commit()
    db.refresh(transcript_file)

