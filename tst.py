from chat import Chat
from config import parse_flags, Config, PropertyKeys
from dotenv import load_dotenv
from logging import basicConfig, getLogger, FileHandler, Formatter, StreamHandler, INFO, DEBUG
from os import path
from workflow import Workflow
from sys import exit


logger = getLogger(__name__)


def initialize() -> Config:
    load_dotenv()
    flags = parse_flags()

    # Set up logging
    if flags.log_file:
        basicConfig(level=DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename=flags.log_file,
                    filemode='a')
        console = StreamHandler()
        console.setLevel(INFO)
        console.setFormatter(Formatter('%(message)s'))
        getLogger('').addHandler(console)
    else:
        basicConfig(level=INFO, format='%(message)s')

    logger.debug('Parsing config')
    config = Config(flags)
    if config.error:
        logger.error('Could not load config: %s' % config.error)
        return None
    return config


def main() -> int:
    config = initialize()
    if not config:
        return 1
    if config.action() == 'PRINT_CONFIG':
        logger.debug('Printing config to standard output')
        print(config)
        return 0

    # If necessary, run a smoke test to verify that the LLM works
    if config.action() == 'SMOKE_TEST':
        chat = Chat(config)
        error = chat.smoke_test()
        if error:
            logger.error('Smoke test failed: %s' % error)
            return 1
        logger.info('Smoke test passed')
        return 0

    # Write X chapter beat
    workflow = Workflow(config)
    if config.action() == 'WRITE_DRAFT':
        output_file, can_overwrite = config.output_file()
        if path.exists(output_file) and not can_overwrite:
            logger.error('File already exists, please delete or add -f parameter: %s' %
                         output_file)
            return 1
        chapter_by_beat = workflow.write_chapter_beats()
        with open(output_file, 'w', encoding=config.encoding()) as f:
            f.write('\n\n'.join(chapter_by_beat))
        logger.info('Chapter was written to %s' % output_file)
        return 0

    # Retain information for the next chapter
    if config.action() == 'UPDATE_METADATA':
        input_file = config.input_file()
        if not path.exists(input_file):
            logger.error('File not found: %s' % input_file)
            return 1
        with open(input_file, 'r', encoding=config.encoding()) as f:
            previous_chapter = f.read()
        # We save the last X words from the previous chapter plus a summary
        chapter_metadata = config.get_properties(
            str(config.chapter_number()), {})
        chapter_metadata[str(PropertyKeys.CHAPTER_SNIPPET)] = (
            config.trim_previous_chapter(previous_chapter))
        chapter_metadata[str(PropertyKeys.CHAPTER_SUMMARY)
                         ] = workflow.write_summary(previous_chapter)
        config.set_properties(config.chapter_number(), chapter_metadata)
        config.save_properties()
        logger.info('Chapter metadata was updated')
        return 0

    logger.fatal('Unknown command: %s' % config.action())
    return 1


if __name__ == '__main__':
    main()
