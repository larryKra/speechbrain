import os
import shutil
from speechbrain.dataio.dataio import read_audio, merge_csvs
from speechbrain.utils.data_utils import download_file

try:
    import pandas as pd
except ImportError:
    err_msg = (
        "The optional dependency pandas must be installed to run this recipe.\n"
    )
    err_msg += "Install using `pip install pandas`.\n"
    raise ImportError(err_msg)


def prepare_TAS(data_folder, type, train_splits):
    """
    This function prepares the Timers and Such dataset.
    If the folder does not exist, the zip file will be extracted. If the zip file does not exist, it will be downloaded.

    data_folder : path to Timers and Such dataset.
    type : one of the following:

      "direct":{input=audio, output=semantics}
      "multistage":{input=audio, output=semantics} (using ASR transcripts in the middle)
      "joint-transcript-semantics":{input=audio, output=transcript+semantics}
      "joint-semantics-transcript":{input=audio, output=semantics+transcript}
      "decoupled":{input=transcript, output=semantics} (using ground-truth transcripts)

    train_splits : list of splits to be joined to form train .csv
    """
    if type == "decoupled":
        try:
            import inflect

            p = inflect.engine()
        except ModuleNotFoundError:
            print(
                'Error: the inflect module must be installed to run the "decoupled" SLU recipe.'
            )
            print("Install using `pip install inflect`.")
            raise

    # If the data folders do not exist, we need to extract the data
    if not os.path.isdir(os.path.join(data_folder, "train-synth")):
        # Check for zip file and download if it doesn't exist
        zip_location = os.path.join(data_folder, "timers-and-such.zip")
        if not os.path.exists(zip_location):
            url = "https://zenodo.org/record/4110812/files/timers-and-such.zip?download=1"
            download_file(url, zip_location, unpack=True)
        else:
            print("Extracting timers-and-such.zip...")
            shutil.unpack_archive(zip_location, data_folder)

    splits = [
        "train-real",
        "dev-real",
        "test-real",
        "train-synth",
        "dev-synth",
        "test-synth",
    ]
    ID_start = 0  # needed to have a unique ID for each audio
    for split in splits:
        new_filename = os.path.join(data_folder, split) + "-type=%s.csv" % type
        if os.path.exists(new_filename):
            continue
        print("Preparing %s..." % new_filename)

        ID = []
        duration = []

        wav = []
        wav_format = []
        wav_opts = []

        spk_id = []
        spk_id_format = []
        spk_id_opts = []

        semantics = []
        semantics_format = []
        semantics_opts = []

        transcript = []
        transcript_format = []
        transcript_opts = []

        df = pd.read_csv(os.path.join(data_folder, split) + ".csv")
        for i in range(len(df)):
            ID.append(ID_start + i)
            signal = read_audio(os.path.join(data_folder, df.path[i]))
            duration.append(signal.shape[0] / 16000)

            wav.append(os.path.join(data_folder, df.path[i]))
            wav_format.append("wav")
            wav_opts.append(None)

            spk_id.append(df.speakerId[i])
            spk_id_format.append("string")
            spk_id_opts.append(None)

            transcript_ = df.transcription[i]
            if type == "decoupled":
                words = transcript_.split()
                for w in range(len(words)):
                    words[w] = words[w].upper()
                    # If the word is numeric, we need to convert it to letters, to match what the ASR would output.
                    if any(c.isdigit() for c in words[w]):
                        if "AM" in words[w] or "PM" in words[w]:
                            AM_or_PM = "A M" if "AM" in words[w] else "P M"
                            if ":" in words[w]:
                                hour = words[w].split(":")[0]
                                minute = (
                                    words[w].split(":")[1].split("AM")[0]
                                    if "AM" in words[w]
                                    else words[w].split(":")[1].split("PM")[0]
                                )
                                words[w] = (
                                    p.number_to_words(hour).upper()
                                    + " "
                                    + p.number_to_words(minute).upper()
                                    + " "
                                    + AM_or_PM
                                )
                            else:
                                hour = (
                                    words[w].split("AM")[0]
                                    if "AM" in words[w]
                                    else words[w].split("PM")[0]
                                )
                                words[w] = (
                                    p.number_to_words(hour).upper()
                                    + " "
                                    + AM_or_PM
                                )
                        else:
                            words[w] = p.number_to_words(words[w]).upper()
                transcript_ = " ".join(words).replace("-", " ")

            transcript.append(transcript_)
            transcript_format.append("string")
            transcript_opts.append(None)

            semantics_ = df.semantics[i].replace(
                ",", "|"
            )  # Commas in dict will make using csv files tricky; replace with pipe.
            semantics_ = semantics_.replace(
                ".3333333333333333", ".33"
            )  # Fix formatting error in some labels
            if type == "direct" or type == "multistage" or type == "decoupled":
                semantics.append(semantics_)
            if type == "joint-transcript-semantics":
                semantics.append(
                    "{'transcript': '" + transcript_ + "'| " + semantics_[1:]
                )
            if type == "joint-semantics-transcript":
                semantics.append(
                    semantics_[:-1] + "| 'transcript': '" + transcript_ + "'}"
                )
            semantics_format.append("string")
            semantics_opts.append(None)

        new_df = pd.DataFrame(
            {
                "ID": ID,
                "duration": duration,
                "wav": wav,
                "wav_format": wav_format,
                "wav_opts": wav_opts,
                "spk_id": spk_id,
                "spk_id_format": spk_id_format,
                "spk_id_opts": spk_id_opts,
                "semantics": semantics,
                "semantics_format": semantics_format,
                "semantics_opts": semantics_opts,
                "transcript": transcript,
                "transcript_format": transcript_format,
                "transcript_opts": transcript_opts,
            }
        )
        new_df.to_csv(new_filename, index=False)
        ID_start += len(df)

    # Merge train splits
    train_splits = [split + "-type=%s.csv" % type for split in train_splits]
    merge_csvs(data_folder, train_splits, "train-type=%s.csv" % type)
