"""
Code execution handler for Desktop Agent.
Parses <code></code> tags and executes Python code.
"""

import re
import asyncio
import tempfile
import os
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class CodeBlock:
    """Represents a code block parsed from <code></code> tags."""
    language: str
    code: str
    raw_content: str


@dataclass
class CodeResult:
    """Represents the result of code execution."""
    code: str
    output: str
    success: bool
    error: str = ""
    execution_time: float = 0.0


class CodeExecutor:
    """Simple code executor for <code></code> blocks."""
    
    def __init__(self, sandbox_config=None):
        """Initialize code executor."""
        self.sandbox_config = sandbox_config or {}
        
        # Simple pattern to match <code></code> blocks
        self.code_pattern = re.compile(
            r'<code>(.*?)</code>', 
            re.DOTALL | re.IGNORECASE
        )
    
    def parse_code_blocks(self, text: str) -> List[CodeBlock]:
        """
        Parse <code></code> tags from text and extract code blocks.
        
        Expected format:
        <code>
        ```python
        print("Hello, World!")
        ```
        </code>
        """
        code_blocks = []
        
        for match in self.code_pattern.finditer(text):
            content = match.group(1).strip()
            raw_content = match.group(0)
            
            # Look for ```language markers
            if content.startswith('```'):
                lines = content.split('\n')
                first_line = lines[0]
                
                # Extract language (if specified)
                language = 'python'  # default
                if len(first_line) > 3:
                    lang_part = first_line[3:].strip()
                    if lang_part:
                        language = lang_part
                
                # Extract code (everything except first and last line)
                if len(lines) >= 2 and lines[-1].strip() == '```':
                    code_lines = lines[1:-1]
                else:
                    code_lines = lines[1:]
                
                code = '\n'.join(code_lines)
            else:
                # No ``` markers, treat as plain code
                language = 'python'
                code = content
            
            # Remove common indentation
            if code.strip():
                code = self._remove_common_indent(code)
                
                code_blocks.append(CodeBlock(
                    language=language.lower(),
                    code=code,
                    raw_content=raw_content
                ))
        
        return code_blocks
    
    def _remove_common_indent(self, code: str) -> str:
        """Remove common leading whitespace from all lines."""
        import textwrap
        return textwrap.dedent(code).strip()
    
    async def execute_python_code(self, code: str) -> CodeResult:
        """Execute Python code using subprocess."""
        import time
        start_time = time.time()
        
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            try:
                # Execute Python script
                process = await asyncio.create_subprocess_exec(
                    'python', temp_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=30
                )
                
                execution_time = time.time() - start_time
                
                # Handle results
                if process.returncode == 0:
                    output = stdout.decode('utf-8', errors='replace')
                    return CodeResult(
                        code=code,
                        output=output,
                        success=True,
                        execution_time=execution_time
                    )
                else:
                    error_output = stderr.decode('utf-8', errors='replace')
                    return CodeResult(
                        code=code,
                        output=error_output,
                        success=False,
                        error=f"Process exited with code {process.returncode}",
                        execution_time=execution_time
                    )
            
            finally:
                # Clean up
                try:
                    os.unlink(temp_file)
                except:
                    pass
                    
        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            return CodeResult(
                code=code,
                output="",
                success=False,
                error="Execution timeout (30 seconds)",
                execution_time=execution_time
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return CodeResult(
                code=code,
                output="",
                success=False,
                error=f"Execution error: {str(e)}",
                execution_time=execution_time
            )
    
    async def execute_code_blocks_in_text(self, text: str) -> Tuple[List[CodeResult], str]:
        """
        Execute all code blocks found in text and return results with cleaned text.
        
        Returns:
            Tuple of (code_results, cleaned_text)
        """
        code_blocks = self.parse_code_blocks(text)
        code_results = []
        
        # Execute code blocks
        for code_block in code_blocks:
            if code_block.language == 'python':
                result = await self.execute_python_code(code_block.code)
                code_results.append(result)
            else:
                # Unsupported language
                code_results.append(CodeResult(
                    code=code_block.code,
                    output="",
                    success=False,
                    error=f"Language '{code_block.language}' is not supported"
                ))
        
        # Replace code blocks with results
        cleaned_text = text
        for i, code_block in enumerate(code_blocks):
            result = code_results[i]
            
            # Format result using <code_output> tags
            if result.success:
                if result.output.strip():
                    result_text = f"{code_block.raw_content}\n\n<code_output>\n{result.output.strip()}\n</code_output>"
                else:
                    result_text = f"{code_block.raw_content}\n\n<code_output>\n(出力なし - 実行時間: {result.execution_time:.3f}秒)\n</code_output>"
            else:
                error_info = f"エラー: {result.error}"
                if result.output.strip():
                    error_info += f"\n{result.output.strip()}"
                error_info += f"\n実行時間: {result.execution_time:.3f}秒"
                result_text = f"{code_block.raw_content}\n\n<code_output>\n{error_info}\n</code_output>"
            
            # Replace code block with code + result
            cleaned_text = cleaned_text.replace(code_block.raw_content, result_text, 1)
        
        return code_results, cleaned_text
    
    def has_code_blocks(self, text: str) -> bool:
        """Check if text contains code blocks."""
        return bool(self.code_pattern.search(text))
    
    def has_complete_code_blocks(self, text: str) -> bool:
        """Check if text contains complete code blocks (with closing </code>)."""
        return bool(self.code_pattern.search(text))
    
    async def extract_and_execute_completed_code_async(self, text: str) -> Tuple[str, bool]:
        """
        Async version: Extract and execute any completed code blocks in the text.
        Returns (modified_text, found_and_executed_code).
        
        This is designed for streaming scenarios where we want to execute
        code as soon as </code> is detected and append results inline.
        """
        if not self.has_complete_code_blocks(text):
            return text, False
        
        # Find complete code blocks
        code_blocks = self.parse_code_blocks(text)
        if not code_blocks:
            return text, False
        
        try:
            # Execute all code blocks
            modified_text = text
            executed_any = False
            
            for code_block in code_blocks:
                if code_block.language == 'python':
                    # Execute asynchronously
                    result = await self.execute_python_code(code_block.code)
                    
                    # Format result using <code_output> tags
                    if result.success:
                        if result.output.strip():
                            result_text = f"\n\n<code_output>\n{result.output.strip()}\n</code_output>\n\n"
                        else:
                            result_text = f"\n\n<code_output>\n(出力なし - 実行時間: {result.execution_time:.3f}秒)\n</code_output>\n\n"
                    else:
                        error_info = f"エラー: {result.error}"
                        if result.output.strip():
                            error_info += f"\n{result.output.strip()}"
                        error_info += f"\n実行時間: {result.execution_time:.3f}秒"
                        result_text = f"\n\n<code_output>\n{error_info}\n</code_output>\n\n"
                    
                    # Add result after the code block (preserving the original code)
                    # This keeps the code and adds the output after it
                    replacement = code_block.raw_content + result_text
                    modified_text = modified_text.replace(code_block.raw_content, replacement, 1)
                    executed_any = True
            
            return modified_text, executed_any
            
        except Exception as e:
            # If execution fails, return original text
            print(f"Error executing code in streaming mode: {e}")
            return text, False


# Test function
async def test_code_execution():
    """Test code execution functionality."""
    executor = CodeExecutor()
    
    test_cases = [
        """
        素数を計算してみましょう：
        
        <code>
        ```python
        # 1から100までの素数を計算
        def is_prime(n):
            if n < 2:
                return False
            for i in range(2, int(n**0.5) + 1):
                if n % i == 0:
                    return False
            return True
        
        primes = [n for n in range(1, 101) if is_prime(n)]
        print(f"1から100までの素数: {primes}")
        print(f"素数の個数: {len(primes)}")
        print(f"素数の合計: {sum(primes)}")
        ```
        </code>
        
        結果は上記の通りです。
        """,
        
        """
        簡単な計算：
        
        <code>
        ```python
        result = 2 + 3 * 4
        print(f"2 + 3 * 4 = {result}")
        ```
        </code>
        """
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"Test case {i}:")
        print(f"{'='*60}")
        
        results, cleaned_text = await executor.execute_code_blocks_in_text(test_case)
        
        print("Results:")
        print(cleaned_text)
        
        print(f"\nExecuted {len(results)} code blocks:")
        for j, result in enumerate(results, 1):
            print(f"  Block {j}: {'Success' if result.success else 'Failed'}")
            if not result.success:
                print(f"    Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(test_code_execution())