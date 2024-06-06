from chat import Chat
from config import parse_flags, Config, PropertyKeys
from dotenv import load_dotenv
from logging import getLogger
from os import path, mkdir
from util import configure_logging
from workflow import Workflow
from shutil import copyfile
from sys import argv


logger = getLogger(__name__)


def initialize() -> Config:
    load_dotenv()
    flags = parse_flags()
    configure_logging(flags.log_file)
    logger.debug("COMMANDLINE: python tst.py %s" % ' '.join(argv))
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
        logger.info('Total approximate word count: %s' %
                    len(' '.join(chapter_by_beat).split()))
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

    # Create the folder and files for the next chapter
    if config.action() == 'NEW_CHAPTER':
        chapter_path = config.chapter_path()
        if path.exists(chapter_path):
            logger.warning('Chapter directory already exists, '
                           'will only check for missing files')
        else:
            logger.info('Making new directory')
            mkdir(chapter_path)
        yaml_path = path.join(chapter_path, 'config.yaml')
        if path.exists(yaml_path):
            logger.warning(
                'config.yaml already exists, leaving it as is')
        else:
            logger.info('Writing config.yaml')
            copyfile('chapter.yaml.template', yaml_path)
        edited_path = config.input_file()
        edited_name = path.split(edited_path)[-1]
        if path.exists(edited_path):
            logger.warning(
                '%s already exists, leaving it as is' % edited_name)
        else:
            logger.info('Writing %s' % edited_name)
            with open(edited_path, 'w', encoding=config.encoding()) as f:
                f.write('Once the chapter is created, '
                        'drop the edited version of it in this file.')
        logger.info('Done. Please run UPDATE_METADATA on the '
                    'previous chapter if you have not yet done so.')
        return 0

    logger.fatal('Unknown command: %s' % config.action())
    return 1


if __name__ == '__main__':
    main()
