"""Member saves Paper, uploads academic paper and retrieves a chapter citation through Chrome."""
from pathlib import Path
import json
import pytest
from test.helpers.accounts import AccountRegistry
from test.helpers.chrome_cdp import ChromeSession
from test.helpers.fake_provider import running_stack_fake_provider
from test.helpers.ingest import upload_text
from test.testcases.conftest import BASE_URL
from test.testcases.test_dataset_flow import create,workspace
from test.testcases.test_provider_flow import api,ok
from test.testcases.test_spa_ingestion_browser import Scene,_press
from test.testcases.test_spa_browser import _set_viewport,_wait_testid,_type_into
from test.testcases.test_spa_chat_browser import range_value

pytestmark=pytest.mark.e2e


def test_saved_paper_choice_and_retrieved_chapter_ancestry(ingress,repo_root):
    accounts=AccountRegistry(BASE_URL)
    try:
        with running_stack_fake_provider() as fake:
            owner=workspace(ingress,accounts,fake,'paper')
            dataset=ok(create(ingress,owner))['id']
            path=repo_root/'test/fixtures/phase6/paper-original.md'
            gold=json.loads(path.with_name('paper-original-annotation.json').read_text())
            doc=upload_text(ingress,owner,dataset,path.read_bytes(),path.name,mime='text/markdown')
            scene=Scene(ingress,owner,fake,dataset)
            with ChromeSession() as browser:
                _set_viewport(browser)
                scene.files(browser)
                _press(browser,'document-more');_press(browser,'document-menu-chunking')
                _wait_testid(browser,'chunk-method-option-paper');_press(browser,'chunk-method-option-paper')
                _press(browser,'chunk-method-submit')
                browser.wait_for('!document.querySelector(\'[data-testid="chunk-method-dialog"]\')','Paper choice saved')
                detail=ok(api(ingress,'GET',f"/api/v1/datasets/{dataset}/documents/{doc['id']}",owner.token))
                assert detail['parser_id']=='paper'
                scene.files(browser)
                _press(browser,'document-more');_press(browser,'document-menu-chunking')
                _wait_testid(browser,'chunk-method-option-paper')
                assert browser.evaluate('document.querySelector(\'[data-testid="chunk-method-option-paper"]\').checked') is True
                browser.evaluate('document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}))')
                scene.parse(doc['id'])
                chunks=ok(api(ingress,'GET',f"/api/v1/datasets/{dataset}/documents/{doc['id']}/chunks",owner.token))
                assert chunks['total']==5
                assert gold['facts'][0] in chunks['items'][0]['text'] and gold['facts'][1] in chunks['items'][1]['text']
                scene.files(browser);_press(browser,'dataset-test-retrieval')
                _wait_testid(browser,'field-retrieval-question')
                _type_into(browser,'field-retrieval-question','What is the calibration offset?')
                range_value(browser,'field-retrieval-threshold',0);range_value(browser,'field-retrieval-weight',0)
                _press(browser,'retrieval-run');_wait_testid(browser,'hit-card');_press(browser,'hit-source')
                browser.wait_for('document.querySelector(\'[data-testid="source-passage"]\')?.textContent.includes("73 units")','chapter citation')
                passage=browser.evaluate('document.querySelector(\'[data-testid="source-passage"]\').textContent')
                assert 'METHOD FACT: calibration offset is 73 units.' in passage and '2 Methods' in passage
                assert '9100' not in passage and 'REFERENCE FACT' not in passage
                assert browser.evaluate('document.querySelectorAll(\'[data-testid="source-passage"] img, [data-testid="source-passage"] script\').length')==0
                browser.wait_for('document.querySelector(\'[data-testid="source-drawer"]\').getAnimations({subtree:true}).every(a=>a.playState!=="running")','source motion settled')
                output=Path('output/playwright/phase6-review');output.mkdir(parents=True,exist_ok=True)
                browser.screenshot(str(output/'academic-paper-source.png'))
    finally:
        accounts.cleanup()
