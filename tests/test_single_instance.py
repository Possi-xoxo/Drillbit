import struct

import pytest

from app.single_instance import (MAX_MESSAGE_BYTES,activation_payload,command_line_files,decode_payload,
    encode_payload,extract_frames,instance_server_name,select_incoming_file,startup_decision)
from app.main_window import MainWindow


def test_instance_name_is_stable_per_identity_and_does_not_expose_identity():
    first=instance_server_name("user-a-secret");second=instance_server_name("user-a-secret")
    assert first==second and first.startswith("Drillbit_") and "user-a-secret" not in first
    assert first!=instance_server_name("user-b-secret")


def test_activation_payload_round_trip_with_no_files():
    framed=encode_payload(activation_payload())
    buffer=bytearray(framed);frames=extract_frames(buffer)
    assert len(frames)==1 and not buffer and decode_payload(frames[0])["files"]==[]


def test_activation_payload_round_trip_with_one_fragmented_file(tmp_path):
    project=tmp_path/"art.drillbit";payload=activation_payload([project]);framed=encode_payload(payload);buffer=bytearray()
    buffer.extend(framed[:3]);assert extract_frames(buffer)==[]
    buffer.extend(framed[3:9]);assert extract_frames(buffer)==[]
    buffer.extend(framed[9:]);frames=extract_frames(buffer)
    assert decode_payload(frames[0])["files"]==[str(project.resolve())] and not buffer


@pytest.mark.parametrize("body",[b"not json",b"[]",b'{"version":1,"action":"wrong","files":[]}',b'{"version":1,"action":"activate","files":[3]}'])
def test_malformed_payload_is_rejected(body):
    assert decode_payload(body) is None


def test_oversized_frame_is_rejected_before_body_arrives():
    with pytest.raises(ValueError):extract_frames(bytearray(struct.pack(">I",MAX_MESSAGE_BYTES+1)))


def test_existing_instance_decision_forwards_without_listening():
    calls=[]
    decision=startup_decision(lambda:calls.append("connect") or True,lambda:calls.append("listen") or True,lambda:False)
    assert decision=="secondary" and calls==["connect"]


def test_first_listener_becomes_primary():
    calls=[]
    decision=startup_decision(lambda:calls.append("connect") or False,lambda:calls.append("listen") or True,lambda:False)
    assert decision=="primary" and calls==["connect","listen"]


def test_near_simultaneous_loser_retries_and_forwards_without_removal():
    connections=iter((False,False,True));removed=[]
    decision=startup_decision(lambda:next(connections),lambda:False,lambda:removed.append(True) or True,retries=3)
    assert decision=="secondary" and removed==[]


def test_stale_endpoint_is_removed_only_after_failed_connect_retries():
    events=[];listen_results=iter((False,True))
    decision=startup_decision(lambda:events.append("connect") or False,lambda:events.append("listen") or next(listen_results),
                              lambda:events.append("remove") or True,retries=2)
    assert decision=="primary" and events==["connect","listen","connect","connect","remove","listen"]


def test_file_selection_validates_existence_type_and_uses_first_supported(tmp_path):
    image=tmp_path/"first.png";project=tmp_path/"second.drillbit";legacy=tmp_path/"old.diamond";image.touch();project.touch();legacy.touch()
    assert select_incoming_file([tmp_path/"missing.png",tmp_path/"bad.txt",image,project])==image
    assert select_incoming_file([project])==project and select_incoming_file([legacy])==legacy
    assert select_incoming_file([tmp_path/"missing.diamond",tmp_path/"bad.txt"]) is None


def test_command_line_file_collection_ignores_switches():
    assert command_line_files(["Drillbit.exe","--test-mode",r"C:\Art\one.drillbit",r"C:\Art\old.diamond"])==[r"C:\Art\one.drillbit",r"C:\Art\old.diamond"]


def test_incoming_file_handoff_respects_unsaved_confirmation(tmp_path):
    image=tmp_path/"incoming.png";image.touch();events=[]
    class Window:
        def activate_existing_window(self):events.append("activate")
        def _confirm_discard(self):events.append("confirm");return False
        def load_path(self,path):events.append(("image",path))
        def load_project_path(self,path):events.append(("project",path))
    MainWindow.handle_activation_request(Window(),[str(image)])
    assert events==["activate","confirm"]
