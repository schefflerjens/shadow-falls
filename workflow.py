from chat import Chat
from config import Config, CommonPrompts, PropertyKeys, Persona
from logging import getLogger
from re import findall
from util import last_sentences, remove_overlap


logger = getLogger()


class Workflow:

    def __init__(self, config: Config) -> None:
        self.__config = config

    def ___new_chat(self, p: Persona) -> Chat:
        chat = Chat(self.__config, p)
        llm_config = self.__config.llm_config(p)
        if llm_config.persona is not None:
            chat.add_system_message(
                self.__config.persona(llm_config)
            )
        return chat

    def __author_chat(self) -> Chat:
        """Create a clean author chat (without chat history)"""
        return self.___new_chat(Persona.AUTHOR)

    def __assistant_chat(self) -> Chat:
        """Create a clean assistant / junior writing partner chat."""
        return self.___new_chat(Persona.ASSISTANT)

    def __editor_chat(self) -> Chat:
        """Create a clean editor chat (without chat history)"""
        return self.___new_chat(Persona.EDITOR)

    def __pick_best(self, prompt: CommonPrompts,
                    drafts: list[str], **kwargs) -> str:
        assert len(drafts), 'Drafts array should never be empty!!!'
        if len(drafts) == 1:
            return drafts[0]
        # Prompt the editor persona to choose the best draft
        versions = []
        for i in range(len(drafts)):
            versions.append('DRAFT %s:\n%s' % (i + 1, drafts[i]))
        editor_pick = self.__editor_chat().chat(self.__config.prompt(
            prompt,
            drafts='\n==================\n'.join(versions),
            **kwargs
        ))
        draft = drafts[0]  # in case the LLM fails to pick
        numbers = findall(r'[0-9]+', editor_pick)
        if numbers and len(numbers):
            for n in numbers:
                number = int(n) - 1
                # Sometimes, an LLM might spit out a number that doesn't refer
                # to a draft, such as
                # "With 100% certainty, I'd pick #1"
                if number >= 0 and number < len(drafts):
                    return drafts[number]
        return draft

    def write_summary(self, chapter: str) -> str:
        """Summarize a given chapter text."""
        drafts = []
        for i in range(self.__config.versions_per_summary()):
            draft = self.__assistant_chat().chat(
                self.__config.prompt(
                    CommonPrompts.SUMMARIZE_STORY,
                    chapter=chapter,
                    previous_summary=self.__config.previous_summary()
                ))
            drafts.append(draft)
        # Pick the best draft
        return self.__pick_best(
            CommonPrompts.SUMMARY_SELECTION,
            drafts,
            chapter=chapter
        )

    def __write_beat(self,
                     current_beat: str,
                     next_beat: str,
                     prior_output: str,
                     prior_beats: str,
                     setting: str) -> str:
        """Write several drafts for the next beat and return the best one."""
        drafts = []
        logger.debug('Writing %s versions of the current beat: %s' % (
            self.__config.versions_per_beat(), current_beat))
        for i in range(self.__config.versions_per_beat()):
            draft = self.__author_chat().chat(self.__config.prompt(
                CommonPrompts.STORY_BEAT,
                previous_scene=prior_output,
                start_with=last_sentences(prior_output, 2),
                current_beat=current_beat,
                next_beat=next_beat,
                prior_beats=prior_beats,
                setting=setting))
            # Some prompts might instruct the LLM to quote the last few
            # sentences of prior_output for consistency.
            # Let's make sure that any such overlap is stripped away.
            draft = remove_overlap(prior_output.strip(), draft.strip()).strip()
            drafts.append(draft)
        # Pick the best draft
        return self.__pick_best(
            CommonPrompts.BEAT_SELECTION,
            drafts,
            previous_scene=prior_output,
            current_beat=current_beat
        )

    def write_chapter_beats(self) -> list[str]:
        """Write a chapter story beat by story beat."""
        output = []
        prior_beats = self.__config.previous_summary()
        if not prior_beats:
            logger.fatal('Error, previous summary not found. '
                         'Did you run the UPDATE_METADATA command?')
            exit(2)
        prior_output = ''
        if self.__config.chapter_number() > 1:
            logger.debug('Fetching prior output from properties.yaml')
            prior_output = self.__config.get_property(
                self.__config.chapter_number() - 1,
                PropertyKeys.CHAPTER_SNIPPET)
            if not prior_output:
                logger.fatal('Error, previous chapter sample not found. '
                             'Did you run the UPDATE_METADATA command?')
                exit(2)
            logger.debug('Prior output: %s' % prior_output)
        settings = self.__config.setting()
        if not settings:
            logger.fatal('Cannot find settings description for this chapter.')
            exit(2)
        else:
            logger.debug('Chapter setting: %s' % settings)
        story_beats = self.__config.story_beats()
        for count, current_beat in enumerate(story_beats):
            logger.info('Writing beat %s of %s' %
                        ((count + 1, len(story_beats))))
            next_beat = '(END OF CHAPTER, consider ending with a cliffhanger)'
            if count + 1 < len(story_beats):
                next_beat = story_beats[count + 1]
            next_output = self.__write_beat(
                current_beat, next_beat, prior_output, prior_beats, settings)
            output.append(next_output)
            prior_beats = self.write_summary('%s\n%s' % (
                prior_beats,
                current_beat,
            ))
            prior_output = self.__config.trim_previous_chapter(next_output)
        return output
