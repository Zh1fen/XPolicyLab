"""Raw episode semantics and optional real LeRobot writer/reader round trips."""
import ast
import dataclasses
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CORE = all(importlib.util.find_spec(name) for name in ('numpy','cv2','h5py'))
if CORE:
    import cv2
    import h5py
    import numpy as np
    from XPolicyLab.utils.episode_input import ConversionInput
    from XPolicyLab.utils.process_data import encode_image_bit, decode_image_bit, get_action_dim


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def raw_fixture(directory, frames=2):
    env = Path(directory) / 'env_cfg'
    (env/'robot').mkdir(parents=True, exist_ok=True)
    (env/'profile.yml').write_text('config:\n  robot: different_robot_name\nobservation:\n  collect_freq: 20\n')
    (env/'robot/_robot_info.json').write_text(json.dumps({'different_robot_name': {'arm_dim':[2,2], 'ee_dim':[1,1]}}))
    path = Path(directory)/'data/Bench/task/profile/data/episode_0.hdf5'
    path.parent.mkdir(parents=True, exist_ok=True)
    colors = np.zeros((frames,8,8,3),dtype=np.uint8);colors[:]=[210,70,20]
    with h5py.File(path,'w') as stream:
        for group in ('state','action'):
            for i,arm in enumerate(('left','right')):
                stream[f'{group}/{arm}_arm_joint_states'] = np.arange(frames*2,dtype=np.float32).reshape(frames,2)+i*10+(100 if group=='action' else 0)
                stream[f'{group}/{arm}_ee_joint_states'] = np.full(frames,i+.5,dtype=np.float32)
        stream['instruction']='singular'
        stream['instructions']=np.asarray(['plural'],dtype=h5py.string_dtype())
        for camera in ('cam_head','cam_left_wrist','cam_right_wrist'):
            bits=encode_image_bit(colors)
            target=stream.create_dataset(f'vision/{camera}/colors',(frames,),dtype=h5py.vlen_dtype(np.dtype('uint8')))
            for index,bit in enumerate(bits):target[index]=np.frombuffer(bit,dtype=np.uint8)
    return env,path,colors


@unittest.skipUnless(CORE, 'requires core image/HDF5 dependencies')
class InputSemanticsTests(unittest.TestCase):
    def facade(self,path,env):
        source=path.read_text();tree=ast.parse(source)
        functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name.startswith('_')]
        namespace=dict(np=np,cv2=cv2,random=random,Path=Path,ConversionInput=ConversionInput,
                       DATA_ROOT=env.parent/'data',ENV_CFG_ROOT=env,ROBOT_INFO_PATH=env/'robot/_robot_info.json',
                       DEFAULT_IMAGE_HEIGHT=8,DEFAULT_IMAGE_WIDTH=8,SUPPORTED_IMAGE_SIZES=((480,640),(240,320)),
                       decode_image_bit=decode_image_bit)
        from XPolicyLab.utils.load_file import load_json,load_yaml
        namespace.update(load_json=load_json,load_yaml=load_yaml)
        camera=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CAMERA_CANDIDATES' for t in n.targets))
        namespace['CAMERA_CANDIDATES']=ast.literal_eval(camera.value)
        # Only pure extraction helpers are evaluated, not any version-specific writer imports.
        module=ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')],level=0),*functions],type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),str(path),'exec'),namespace)
        return namespace

    def test_before_after_fields_pixels_instruction_priority_and_padding(self):
        from XPolicyLab.utils.load_file import load_hdf5
        with tempfile.TemporaryDirectory() as directory:
            env,path,_=raw_fixture(directory);data=load_hdf5(path)
            baseline=ROOT/'artifacts/architecture-qa/baseline'
            for version,expected in ((21,'plural'),(30,'singular')):
                before_path=baseline/f'scripts/transform_lerobot_v{version}_format.py'
                before=self.facade(before_path if before_path.exists() else ROOT/f'scripts/transform_lerobot_v{version}_format.py',env)
                after=self.facade(ROOT/f'scripts/transform_lerobot_v{version}_format.py',env)
                for function in ('_extract_qpos','_extract_action'):
                    np.testing.assert_array_equal(before[function](data),after[function](data))
                random.seed(11);old=before['_choose_instruction'](data)
                random.seed(11);new=after['_choose_instruction'](data)
                self.assertEqual((old,new),(expected,expected))
                state=after['_extract_qpos'](data)
                np.testing.assert_array_equal(before['_pad_state_to_target_dims'](state,[3,3],[4,5],'state'),after['_pad_state_to_target_dims'](state,[3,3],[4,5],'state'))
                for camera in after['CAMERA_CANDIDATES']:
                    np.testing.assert_array_equal(before['_find_camera_array'](data,camera,8,8),after['_find_camera_array'](data,camera,8,8))
                self.assertEqual(after['_load_env_metadata']('profile')[0],'different_robot_name')

    def test_robot_dimensions_and_independent_training_shell_agree(self):
        with tempfile.TemporaryDirectory() as directory:
            env,_,_=raw_fixture(directory)
            (Path(directory)/'XPolicyLab/utils/robot').mkdir(parents=True)
            (Path(directory)/'XPolicyLab/utils/robot/_robot_info.json').write_text(json.dumps({'profile':{'arm_dim':[2,2],'ee_dim':[1,1]}}))
            runtime=get_action_dim('profile',env_cfg_root=env)
            process=subprocess.run(['bash',str(ROOT/'utils/get_action_dim.sh'),directory,'profile'],capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(runtime,int(process.stdout))
            self.assertFalse((ROOT/'env_cfg').exists())

    def test_pi05_next_state_actions_and_aloha_qpos_fallback_stay_distinct(self):
        pi=load_module(ROOT/'policy/Pi_05/openpi/scripts/process_data.py','qa_pi_data')
        aloha=load_module(ROOT/'scripts/transform_aloha_hdf5_format.py','qa_aloha_data')
        state=np.arange(12,dtype=np.float32).reshape(3,4)
        np.testing.assert_array_equal(pi._make_action_from_state(state),state[[1,2,2]])
        np.testing.assert_array_equal(pi._make_action_from_state(state[:1]),state[:1])
        with self.assertRaises(ValueError):pi._make_action_from_state(state[:0])
        np.testing.assert_array_equal(aloha._extract_action({},state),np.concatenate([state[1:],np.zeros_like(state[:1])]))
        with tempfile.TemporaryDirectory() as directory:
            _,path,_=raw_fixture(directory)
            episode=pi.load_data(path)
            self.assertEqual(episode['instructions'],['plural'])
            self.assertEqual(episode['state'].dtype,np.float32)
            self.assertEqual(set(episode['images']),{'cam_high','cam_left_wrist','cam_right_wrist'})

    def test_decode_import_does_not_require_hdf5(self):
        script="import sys;from XPolicyLab.utils.process_data import decode_image_bit;assert 'h5py' not in sys.modules"
        process=subprocess.run([sys.executable,'-c',script],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(process.returncode,0,process.stderr)


@unittest.skipUnless(CORE and os.environ.get('ROBOLAB_CONVERSION_VERSION'), 'set ROBOLAB_CONVERSION_VERSION=21 or 30 in its writer environment')
class RealDatasetTests(unittest.TestCase):
    def test_public_converter_round_trip_with_its_own_reader(self):
        version=int(os.environ['ROBOLAB_CONVERSION_VERSION'])
        module=load_module(ROOT/f'scripts/transform_lerobot_v{version}_format.py',f'qa_writer{version}')
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
        with tempfile.TemporaryDirectory() as directory:
            env,path,_=raw_fixture(directory)
            output=Path(directory)/'output'
            module.HF_LEROBOT_HOME=output
            config=dataclasses.replace(module.DEFAULT_DATASET_CONFIG,use_videos=False,image_writer_processes=0,image_writer_threads=1)
            dataset=module.create_empty_dataset(repo_id='fixture',robot_type='fixture',motors=[str(i) for i in range(6)],fps=20,mode='image',image_height=8,image_width=8,dataset_config=config)
            module.convert_one(path,dataset,'xspark','v1.0',[3,3],[3,3],8,8)
            if version==30:module.finalize_dataset(dataset)
            from XPolicyLab.utils.load_file import load_hdf5
            source=load_hdf5(path);reader=module._input_reader()
            loaded=LeRobotDataset('fixture',root=output/'fixture')
            self.assertEqual(len(loaded),2)
            np.testing.assert_array_equal(loaded[0]['observation.state'].numpy(),reader._extract_qpos(source)[0])
            np.testing.assert_array_equal(loaded[0]['action'].numpy(),reader._extract_action(source)[0])
            pixels=loaded[0]['observation.images.cam_high'].numpy().transpose(1,2,0)*255
            np.testing.assert_allclose(pixels,decode_image_bit(source['vision']['cam_head']['colors'])[0],atol=1)
            self.assertEqual(loaded[0]['task'],'plural' if version==21 else 'singular')

    def test_pi05_public_shell_round_trip_and_empty_input_failure(self):
        if os.environ['ROBOLAB_CONVERSION_VERSION']!='30':
            self.skipTest('Pi_05 uses the installed LeRobot v3 API')
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
        with tempfile.TemporaryDirectory() as directory:
            env,path,_=raw_fixture(directory)
            args=['bash',str(ROOT/'policy/Pi_05/process_data.sh'),'Bench','task','profile','joint','--input-root',str(Path(directory)/'data'),'--env-cfg-root',str(env),'--output-root',str(Path(directory)/'output')]
            process=subprocess.run(args,cwd='/tmp',env=dict(os.environ,OPENPI_DATA_PYTHON=sys.executable),capture_output=True,text=True,timeout=45)
            self.assertEqual(process.returncode,0,process.stderr)
            output=Path(directory)/'output/Bench-task-profile-joint'
            dataset=LeRobotDataset('Bench-task-profile-joint',root=output)
            self.assertEqual(len(dataset),2)
            self.assertEqual(dataset.meta.total_episodes,1)
            np.testing.assert_array_equal(dataset[0]['action'].numpy(),dataset[1]['observation.state'].numpy())
            self.assertEqual(dataset[0]['task'],'plural')
            self.assertEqual(dataset.meta.fps,20)
            np.testing.assert_array_equal(dataset[1]['action'].numpy(),dataset[1]['observation.state'].numpy())
            from XPolicyLab.utils.load_file import load_hdf5
            source=load_hdf5(path)
            pixels=dataset[0]['observation.images.cam_high'].numpy().transpose(1,2,0)*255
            np.testing.assert_allclose(pixels,decode_image_bit(source['vision']['cam_head']['colors'])[0],atol=1)
            args[3]='missing'
            failed=subprocess.run(args,cwd='/tmp',env=dict(os.environ,OPENPI_DATA_PYTHON=sys.executable),capture_output=True,text=True,timeout=20)
            self.assertNotEqual(failed.returncode,0)
            self.assertIn('未找到',failed.stderr)


if __name__=='__main__':unittest.main()
