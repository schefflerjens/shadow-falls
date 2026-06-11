# shadow-falls (Deprecated Original Engine)

> [!WARNING]
> **OBSOLETE**: The custom Python writing assistant engine in this directory is now deprecated and obsolete. 
> The book has been fully converted into the standard GitBook format under `../Shadow Falls.gitbook/` and is managed by the Homer MCP server. This code is preserved here for historical context only.

A writing assistant for fiction writing, named after the toy book project 
[Shadow falls](https://www.royalroad.com/fiction/87291/shadow-falls) that was generated
to test out the various iterations of the project.

The purpose of the script is to create first drafts of book chapters that stay consistent
in style, setting, and character development. Each of the first few chapters represents
a new teration. For example, 
[chapter 1](https://www.royalroad.com/fiction/87291/shadow-falls/chapter/1653030/dead-end-chase)
was still written using Llama 3, and the limited context window and non-ideal prompts
earned it the glowing feedback, *"I have no idea what the hell I just read."*
[Chapter 2](https://www.royalroad.com/fiction/87291/shadow-falls/chapter/1653882/its-gotta-be-me)
was the first iteration using Gemini 1.5 flash, while the next few chapters mostly focused
on tweaking the prompts and improving consistecy between the "beats", smaller parts of a chapter
that the LLM would write individually. By 
[chapter 5](https://www.royalroad.com/fiction/87291/shadow-falls/chapter/1659487/the-doll),
the formula was "good enough" for now, which was a good time to clean up the code a bit and
make it public.

**Note:** This project is a work in progress. You can use it for your own writing, experiment with
it and make it better. All I ask is if you find a bug, a prompt that works better, or another
imrpovement that produces better prose, please share it back with me :-)

*This project is licensed under the terms of the MIT license.*

## Let's write a new chapter
The following describes all the steps performed to create Chapter 7, the last example
chapter in this repository.

### Initial setup
Before we begin, we need to make sure that we can connect to the Gemini API. If you haven't
done so yet, [create an API key](https://makersuite.google.com/app/apikey). You can store this
key either in an environment variable called `GOOGLE_API_KEY` or you can create a
[`.env` file](https://dev.to/jakewitcher/using-env-files-for-environment-variables-in-python-applications-55a1)
in the root folder of this project that contains an entry

`GOOGLE_API_KEY=your_api_key`

Afterwards, you can test the API connection using the following command:

`python .\assistant.py -p series -c 1 -a SMOKE_TEST`

If you are planning to use Clause, follow 
[this documentation](https://docs.anthropic.com/en/docs/quickstart) to generate a key,
store it under the `ANTHROPIC_API_KEY`environment variable, and run the smoke test with it.
To do so, go to the root `config.yaml` and choose one of the Anthropic models, such as
Claude Sonnet.


### Creating chapter directory ([diff](https://github.com/schefflerjens/shadow-falls/commit/a17242ef92db74df29b3d6b6d9412aa47a248cca))
Using the following command, out script will create a new subfolder with a `config.yaml`
and an empty `edited.txt`. The latter will eventually contain the finalized version
of the chapter.

`python .\assistant.py -p series -c 7 -a NEW_CHAPTER`

### Updating metadata ([diff](https://github.com/schefflerjens/shadow-falls/commit/c4b351b7e8b6c93f0a4d3bf92dc4ed1328dc94c3#diff-7e415b989614b025b4215f8a16759f0371e8323096e9bc1f28da9c9cc4d8c750))
In order to write a new chapter, the script needs some information about what has happened
in the story so far. In particular, we need
* The last N words of the previous chapter as a writing sample for consistency.
* A summary of what happened in the story so far.

While the text of the previous chapter could be obtained on the fly, the summary is a bit
more tricky. To generate the summary, the script would need information of ALL previous
chapters. Depending on how big the overall book is, pulling in that much content would
explode the context window of many LLMs. For that reason, we precompute the summary based
on the last chapter and a summary of what has happened so far. We then store the data in
a project-level file called [`properties.yaml`](https://github.com/schefflerjens/shadow-falls/blob/main/series/properties.yaml).

The following command summarizes chapter 6 (notice the `-c 6` parameter). We need to do this
once before writing the draft for chapter 7:

`python .\assistant.py -p series -c 6 -a UPDATE_METADATA`

### Outlining the chapter ([diff](https://github.com/schefflerjens/shadow-falls/commit/298fc7a65efad7255e0abc8aae1a92f42d1e9f5a))
Before our LLM can write the chapter, we need to provide some information on
what is supposed to happen in it. More precisely, our chapter's 
`config.yaml` needs the following:
* a list of "story beats", a step by step description of what should happen
  in the chapter.
* one or more "environment" entries (settings of where the chapter takes place). The description for
  the environments can be found in the project-level [`config.yaml`](https://github.com/schefflerjens/shadow-falls/blob/main/series/config.yaml).
* optionaly, descriptions of newly introduced characters. In this example, we are adding the
  *Murder Twins*.

### Writing a first draft ([diff](https://github.com/schefflerjens/shadow-falls/commit/589bf1cae6a60bcfdba0191e24bbeced07e805f5))
We now have evrything ready to let the LLM write us a new chapter. For this, we use the following
command:

`python .\assistant.py -p series -c 7 -a WRITE_DRAFT`

Once the command is complete, we will see a new file `out.txt` in the chapter directory. This file
contains the output as we receive it from the LLM. We can now load the output into our favorite
text editor and work on it to turn it into a decent first shot at the new chapter. We store this
edited document in the `edited.txt` file in the same folder. `edited.txt` will serve as input when
we create the chapter summary for chapter 8 with the `UPDATE_METADATA` command.

## Creating a new series

The simplest way is to copy the `series` folder to a new location, delete all the chapter folders,
and run

`python .\assistant.py -p your_new_project_folder -c 1 -a NEW_CHAPTER`

Then, adjust things such as writing style or characters in the project's 
[config.yaml](https://github.com/schefflerjens/shadow-falls/blob/main/series/config.yaml)
and follow the aforementioned steps to write your first chapter.
