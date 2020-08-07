#!/home/joao/code/projects/cephbuild-shell/venv/bin/python3
#
# Copyright (C) 2020  Joao Eduardo Luis <joao@wipwd.dev>
#
# This file is part of WIP:WD's silly build-shell project (wwd-sbs).
# wwd-sbs is free software: you can redistribute it and/or modify it
# under the terms of the EUROPEAN UNION PUBLIC LICENSE v1.2, as published by
# the European Comission.
#
from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.containers import (
    VSplit, Window, HSplit, to_container
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.application import get_app
from prompt_toolkit.widgets import (
    Frame, ProgressBar, Label, HorizontalLine, VerticalLine, TextArea
)

import asyncio
import sys
import re
from typing import Dict

import psutil


progress_bar = ProgressBar()
progress_bar.percentage = 0
progress_bar.label = Label(f"0%")


hitmiss_frame = TextArea(multiline=True)
stats_frame = TextArea(multiline=True)

ccache_frame = VSplit([
    hitmiss_frame,
    VerticalLine(),
    stats_frame,
])
cpu_frame = VSplit([])

ncpus = psutil.cpu_count()
stats_frame.text = f"ncpus: {ncpus}"

cpu_labels: Dict[int, Label] = {}
for i in range(0, ncpus):
    cpu_labels[i] = Label("")

cpu_labels_container = []
curr_cpu_split = None
ndiv = 4 if ncpus > 4 else 1

for i in range(0, ncpus):
    if i == 0 or i%ndiv == 0:
        curr_cpu_split = HSplit([])
        cpu_frame.children.append(curr_cpu_split)
    curr_cpu_split.children.append(to_container(cpu_labels[i]))


compiler_buffer = Buffer()
compiler_window = Window(content=BufferControl(buffer=compiler_buffer))

root_container = HSplit([
    Frame(body=compiler_window),
    VSplit([
        Frame(body=ccache_frame, title="ccache", height=4),
        Frame(body=cpu_frame, title="resource usage")
    ]),
    Frame(body=progress_bar, title="progress"),
])

print(root_container)

layout = Layout(root_container)
kb = KeyBindings()

@kb.add('c-q')
def exit_event(event):
    event.app.exit()

# @kb.add('c-left')
# def change_window_left(event):
#     get_app().layout.focus(window_left)

# @kb.add('c-right')
# def change_window_right(event):
#     get_app().layout.focus(window_right)


async def get_ccache():
    cmd = 'ceph-ccache master --print-stats'.split()
    try:
        proc = await asyncio.create_subprocess_exec(*cmd,
            stdout=asyncio.subprocess.PIPE)
    except Exception as e:
        print(str(e))

    stats = {}
    while True:
        data = await proc.stdout.readline()
        if not data:
            break
        line = data.decode('ascii').rstrip()
        match = re.match("^([a-zA-Z_]+)[ \t]+(\d+)$", line)
        if match:
            stats[match.group(1)] = match.group(2)
    return stats

async def do_compilation():

    try:
        cmd = 'ceph-make -j13'.split()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            # 'bash', './console-text.sh',
            stdout=asyncio.subprocess.PIPE
        )
    except Exception as e:
        compiler_buffer.insert_text(str(e))
        print(e)
    
    compiler_buffer.insert_line_below()
    compiler_buffer.insert_text("starting...\n")
    while True:
        data = await proc.stdout.readline()
        if not data:
            break
        line = data.decode('ascii').rstrip()

        match = re.match("^\[[ ]*(\d+)%\] (.*)$", line)
        if match:
            progress = int(match.group(1))
            line = match.group(2)
            progress_bar.percentage = progress
            progress_bar.label = Label(f"{progress}")

        compiler_buffer.insert_text(line)
        compiler_buffer.newline()
    await proc.wait()
    compiler_buffer.insert_line_below()
    compiler_buffer.insert_text("done?")


async def do_ccache():

    while True:
        # ccache_buffer.reset()
        stats = await get_ccache()
        if stats:
            hitmiss_frame.text = \
f"""hit: {stats['direct_cache_hit']}
miss: {stats['cache_miss']}"""
        await asyncio.sleep(1)


def update_cpu_label(cpu: int, load: int):
    assert cpu < 16
    assert cpu in cpu_labels
    text = f"cpu {cpu:>2}: {load:>3}%"
    cpu_labels[cpu].text = text


async def do_resources():

    while True:
        i = 0
        for load in psutil.cpu_percent(interval=1, percpu=True):
            update_cpu_label(i, round(load))
            i = i + 1

        await asyncio.sleep(0.25)

async def main():

    app = Application(layout=layout, full_screen=True, key_bindings=kb)
    t = app.run_async()
    try:
        # compiler_buffer.insert_text("creating task...\n")
        left_task = asyncio.create_task(do_compilation())
        ccache_task = asyncio.create_task(do_ccache())
        resources_task = asyncio.create_task(do_resources())
        # compiler_buffer.insert_text("created task.\n")
    except Exception as e:
        compiler_buffer.insert_text(str(e))
    await t

asyncio.get_event_loop().run_until_complete(main())
