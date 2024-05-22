from chat import Chat
from config import parse_flags, Config, PropertyKeys
from dotenv import load_dotenv
from os import path
from workflow import Workflow
from sys import exit

# Google API key info
load_dotenv()

# Load the config and check whether we are just supposed to print it.
config = Config(parse_flags())
if config.error:
    exit('Could not load config: %s' % config.error)
if config.action() == 'PRINT_CONFIG':
    print(config)
    exit()

# If necessary, run a smoke test to verify that the LLM works
if config.action() == 'SMOKE_TEST':
    chat = Chat(config)
    error = chat.smoke_test()
    if error:
        exit('Smoke test failed: %s' % error)
    print('Smoke test passed')
    exit()

# Write X chapter beat
workflow = Workflow(config)
if config.action() == 'WRITE_DRAFT':
    output_file, can_overwrite = config.output_file()
    if path.exists(output_file) and not can_overwrite:
        exit('File already exists, please delete or add -f parameter: %s' %
             output_file)
    chapter_by_beat = workflow.write_chapter_beats()
    with open(output_file, 'w', encoding=config.encoding()) as f:
        f.write('\n\n'.join(chapter_by_beat))
    print('Chapter was written to %s' % output_file)
    exit()

# Retain information for the next chapter
if config.action() == 'UPDATE_METADATA':
    input_file = config.input_file()
    if not path.exists(input_file):
        exit('File not found: %s' % input_file)
    with open(input_file, 'r', encoding=config.encoding()) as f:
        previous_chapter = f.read()
    # We save the last X words from the previous chapter plus a summary
    chapter_metadata = config.get_properties(str(config.chapter_number()), {})
    chapter_metadata[str(PropertyKeys.CHAPTER_SNIPPET)] = (
        config.trim_previous_chapter(previous_chapter))
    chapter_metadata[str(PropertyKeys.CHAPTER_SUMMARY)] = workflow.write_summary(previous_chapter)
    config.set_properties(config.chapter_number(), chapter_metadata)
    config.save_properties()
    print('Chapter metadata was updated')
    exit()

exit('Unknown command: %s' % config.action())
