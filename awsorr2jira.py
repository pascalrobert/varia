#!/usr/bin/env python3

""" 
This script will scrape the SVG from https://wa.aws.amazon.com/wat.map.en.html, and create a epic in Jira for each pillar,
a story for each child of the pillar, and a sub-task for each grandchild of the pillar.

© Pascal Robert 2024, https://github.com/pascalrobert/
"""

import requests
from bs4 import BeautifulSoup
import re
from jira import JIRA
import sys
import json
import getpass
import argparse

def get_coordinates(attributes):
    coordinates = attributes.get("transform")
    if coordinates:
        x_and_y = re.match(r'translate\(([0-9,.]+),\s+([0-9,.]+)\)',
                           coordinates)
        if x_and_y:
            x1 = float(x_and_y.group(1))
            y1 = float(x_and_y.group(2))
            return x1, y1
    return None, None


def get_details(base_url, element, is_area):
    x_point, y_point = get_coordinates(element.attrs)
    names = element.find_all("text")
    links = element.find_all("a")
    summary = ""
    for name in names:
        summary = summary + " " + name.string
    if element.title:
        description = element.title.text.replace("\n", "").strip()
        for link in links:
            href = link.attrs.get("xlink:href")
            if not is_area:
                full_page = requests.get(base_url + "/" + href)
                if full_page.status_code == 200:
                    link_content = BeautifulSoup(full_page.content, "lxml")
                    main_div = link_content.find(id="main")
                    if main_div is not None:
                        title_element = main_div.find("h1")
                        if title_element is not None:
                            summary = title_element.text
                            description_element = main_div.find(
                                "h1").find_next_sibling("p")
                            if description_element is not None:
                                description = description_element.text
                            h2s = main_div.find_all("h2")
                            for h2 in h2s:
                                if h2.text == "Ressources":
                                    resources_links = h2.parent.find_all("a")
                                    for resource in resources_links:
                                        description = description + \
                                            "\n\n[" + resource.text.replace("\n", "").strip() + "|" + \
                                            resource.attrs.get("href") + "]"
            else:
                description = description + \
                    "\n\n[" + link.text.replace("\n", "").strip() + "|" + \
                    base_url + "/" + href + "]"
    else:
        description = None
    summary = summary.strip().replace("\n", "")
    if description is not None and x_point is not None:
        return {"summary": summary,
                "description": description, "x1": x_point, "y1": y_point}
    return None


def get_epic(base_url, document, element_id):
    element = document.find(
        "g", id=element_id, class_="pillar")
    return get_details(base_url, element, False)

def main():
    jira = JIRA(server=f"{jira_url}",
                basic_auth=(f"{jira_user}", f"{jira_pass}"))
    base_url = "https://wa.aws.amazon.com"
    result = requests.get(base_url + "/wat.map.en.html")
    if result.status_code == 200:
        document = BeautifulSoup(result.content, "lxml")
        lines = document.find_all("line")
        lines_coordinates = []
        
        for line in lines:
            lines_coordinates.append({"x1": float(line.attrs.get("x1")), "x2": float(line.attrs.get(
                "x2")), "y1": float(line.attrs.get("y1")), "y2": float(line.attrs.get("y2"))})

        stories = []
        areas = document.find_all("g", class_="area")
        for area in areas:
            story = get_details(base_url, area, True)
            stories.append(story)

        subtasks = []
        sub_areas = document.find_all("g", class_='')
        for sub_area in sub_areas:
            subtask = get_details(base_url, sub_area, False)
            if subtask is not None:
                subtasks.append(subtask)

        epics = []
        epics.append(get_epic(base_url, document, "sustainability"))
        epics.append(get_epic(base_url, document, "costOptimization"))
        epics.append(get_epic(base_url, document, "performance"))
        epics.append(get_epic(base_url, document, "reliability"))
        epics.append(get_epic(base_url, document, "operationalExcellence"))
        epics.append(get_epic(base_url, document, "security"))

        for epic in epics:
            connections = list(filter(
                lambda lines_coordinates: (lines_coordinates["x1"] == epic["x1"] and lines_coordinates["y1"] == epic["y1"]), lines_coordinates))

            epic_issue = jira.create_issue(
                project=f'{jira_project}', summary=epic['summary'], description=epic['description'], issuetype={'name': 'Epic'})

            stories_for_epic = []
            for connection in connections:
                result = list(filter(
                    lambda stories: (stories["x1"] == connection["x2"] and stories["y1"] == connection["y2"]), stories))
                stories_for_epic.extend(result)

            for story in stories_for_epic:
                stories_connections = list(filter(lambda lines_coordinates: (
                    lines_coordinates["x1"] == story["x1"] and lines_coordinates["y1"] == story["y1"]), lines_coordinates))
 
                subtasks_for_story = []
 
                story_issue = jira.create_issue(
                    project=f'{jira_project}', summary=story['summary'], description=story['description'], parent={'key': epic_issue.key}, issuetype={'name': 'Story'}, customfield_10026=componentId)
 
                for story_connection in stories_connections:
                    if story_connection["x2"] is not None and story_connection["y2"] is not None:
                        try:
                            result = list(filter(lambda subtasks: (
                                subtasks["x1"] == story_connection["x2"] and subtasks["y1"] == story_connection["y2"]), subtasks))
                            subtasks_for_story.extend(result)
                        except TypeError:
                            print("not a subtask")

                for subtask_for_story in subtasks_for_story:
                    jira.create_issue(
                        project=f'{jira_project}', summary=subtask_for_story['summary'], description=subtask_for_story['description'], issuetype={'name': 'Subtask'}, parent={'key': story_issue.key})

parser=argparse.ArgumentParser()
parser.add_argument("--jira_user", help="Username to connect to Jira")
parser.add_argument("--jira_url", help="URL to your Jira instance")
parser.add_argument("--jira_project", help="Key of the Jira project to import the issues into")
args=parser.parse_args()

jira_pass = getpass(prompt='Password or token for Jira: ')
jira_user = args.jira_user
jira_url = args.jira_url
jira_project = args.jira_project

if __name__ == '__main__':
    sys.exit(main())