import logging
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from ghostcoder.schema import VerificationFailureItem, VerificationResult
from ghostcoder.verify.verifier import Verifier


class PythonUnittestVerifier(Verifier):

    def __init__(self,
                 test_file_pattern: str = "*.py",
                 current_dir: Optional[Path] = None,
                 timeout: Optional[int] = 5):
        self.test_file_pattern = test_file_pattern
        self.timeout = timeout

        if current_dir:
            self.current_dir = Path(current_dir)
        else:
            self.current_dir = Path(os.getcwd())

    def verify(self) -> VerificationResult:
        command = [
            "python",
            "-m",
            "unittest",
            "discover",
            "-p",
            self.test_file_pattern,
        ]

        command_str = " ".join(command)

        logging.info(f"verify() Run tests with command `$ {command_str}` in {self.current_dir}")

        try:
            result = subprocess.run(
                command,
                cwd=self.current_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=self.timeout)
        except subprocess.TimeoutExpired:
            logging.info(f"verify(): Tests timed out after {self.timeout} seconds.")
            return VerificationResult(
                success=False,
                message=f"Tests timed out after {self.timeout} seconds."
            )

        output = result.stdout

        failed_tests_count, total_test_count = self.parse_test_results(output)

        if result.returncode != 0:
            if failed_tests_count > 0:
                failed_tests = self.find_failed_tests(output)
                logging.info(f"verify(): {failed_tests_count} out of {total_test_count} tests failed.")
                return VerificationResult(
                    success=False,
                    message=f"{failed_tests_count} out of {total_test_count} tests failed.",
                    failures=failed_tests
                )
            else:
                logging.warning(f"verify(): Tests failed to run. \nOutput from {command_str}:\n{output}")
                return VerificationResult(
                    success=False,
                    message=f"Tests failed to run.",
                    failures=[VerificationFailureItem(output=output)]
                )
        else:
            logging.info(f"verify(): All {total_test_count} tests passed.")
            return VerificationResult(
                success=True,
                message=f"All {total_test_count} tests passed."
            )

    def find_failed_tests(self, output: str) -> List[VerificationFailureItem]:
        sections = output.split("======================================================================")
        failed_tests = [self.extract_test_details(section) for section in sections]
        return [test for test in failed_tests if test is not None]

    def extract_test_details(self, section: str) -> Optional[VerificationFailureItem]:
        header_pattern = r'(FAIL|ERROR): ([^\s]+) \(([^.]+)\.([^\.]+)\.([^\)]+)\)'
        body_pattern = r'[\s\S]+?.*File "([^"]+)", (.*)'

        splitted = section.split("----------------------------------------------------------------------")
        if len(splitted) >= 2:
            if "unittest.loader" in splitted[0]:
                test_load_fail = True
            else:
                test_load_fail = False

            header_match = re.search(header_pattern, splitted[0], re.DOTALL)
            body_match = re.search(body_pattern, splitted[1], re.DOTALL)
            if header_match and body_match:
                if test_load_fail:
                    test_result, test_method, _, _, _ = header_match.groups()
                    traceback = splitted[1]
                    test_class = None
                    test_file = None
                else:
                    test_result, test_method, module, test_class, _ = header_match.groups()
                    file_path, traceback = body_match.groups()
                    test_file = file_path.replace(str(self.current_dir) + "/", "")

                return VerificationFailureItem(
                    test_method=test_method,
                    test_class=test_class,
                    test_file=test_file,
                    output=traceback.strip()
                )

        return None

    def parse_test_results(self, test_output):
        total_tests_pattern = r"Ran (\d+) tests"
        failed_tests_pattern = r"FAIL:"
        error_tests_pattern = r"ERROR:"

        total_tests_match = re.search(total_tests_pattern, test_output)
        total_tests = int(total_tests_match.group(1)) if total_tests_match else 0

        failed_tests_count = len(re.findall(failed_tests_pattern, test_output))
        error_tests_count = len(re.findall(error_tests_pattern, test_output))

        total_failed = failed_tests_count + error_tests_count

        return total_failed, total_tests

if __name__ == "__main__":
    verifier = PythonUnittestVerifier(test_file_pattern="*_test.py")

    items = verifier.verify()

    if items:
        print("Failed tests:")
        for item in items:
            print(f"- {item.test_file}:{item.test_class}:{item.test_method}")
